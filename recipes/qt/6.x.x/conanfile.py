import os
import glob
import textwrap

import configparser
from conans import ConanFile, tools, RunEnvironment, CMake
from conans.errors import ConanInvalidConfiguration
from conans.model import Generator

required_conan_version = ">=1.33.0"


class qt(Generator):
    @staticmethod
    def content_template(path, folder, os_):
        return textwrap.dedent("""\
            [Paths]
            Prefix = {0}
            ArchData = {1}/archdatadir
            HostData = {1}/archdatadir
            Data = {1}/datadir
            Sysconf = {1}/sysconfdir
            LibraryExecutables = {1}/archdatadir/bin
            HostLibraryExecutables = {2}
            Plugins = {1}/archdatadir/plugins
            Imports = {1}/archdatadir/imports
            Qml2Imports = {1}/archdatadir/qml
            Translations = {1}/datadir/translations
            Documentation = {1}/datadir/doc
            Examples = {1}/datadir/examples""").format(path, folder, "bin" if os_ == "Windows" else "lib")

    @property
    def filename(self):
        return "qt.conf"

    @property
    def content(self):
        return qt.content_template(
            self.conanfile.deps_cpp_info["qt"].rootpath.replace("\\", "/"),
            "res",
            self.conanfile.settings.os)


class QtConan(ConanFile):
    _submodules = ["qtsvg", "qtdeclarative", "qttools", "qttranslations", "qtdoc",
                   "qtwayland", "qtquickcontrols2", "qtquicktimeline", "qtquick3d", "qtshadertools", "qt5compat",
                   "qtactiveqt", "qtcharts", "qtdatavis3d", "qtlottie", "qtscxml", "qtvirtualkeyboard",
                   "qt3d", "qtimageformats", "qtnetworkauth", "qtcoap", "qtmqtt", "qtopcua"]

    generators = "pkg_config", "cmake_find_package", "cmake"
    name = "qt"
    description = "Qt is a cross-platform framework for graphical user interfaces."
    topics = ("conan", "qt", "ui")
    url = "https://github.com/conan-io/conan-center-index"
    homepage = "https://www.qt.io"
    license = "LGPL-3.0"
    exports = ["patches/*.diff"]
    settings = "os", "arch", "compiler", "build_type"

    options = {
        "shared": [True, False],
        "opengl": ["no", "desktop", "dynamic"],
        "with_vulkan": [True, False],
        "openssl": [True, False],
        "with_pcre2": [True, False],
        "with_glib": [True, False],
        "with_doubleconversion": [True, False],
        "with_freetype": [True, False],
        "with_fontconfig": [True, False],
        "with_icu": [True, False],
        "with_harfbuzz": [True, False],
        "with_libjpeg": ["libjpeg", "libjpeg-turbo", False],
        "with_libpng": [True, False],
        "with_sqlite3": [True, False],
        "with_mysql": [True, False],
        "with_pq": [True, False],
        "with_odbc": [True, False],
        "with_zstd": [True, False],
        "with_brotli": [True, False],

        "gui": [True, False],
        "widgets": [True, False],

        "device": "ANY",
        "cross_compile": "ANY",
        "sysroot": "ANY",
        "multiconfiguration": [True, False],
    }
    options.update({module: [True, False] for module in _submodules})

    # this significantly speeds up windows builds
    no_copy_source = True

    default_options = {
        "shared": False,
        "opengl": "desktop",
        "with_vulkan": False,
        "openssl": True,
        "with_pcre2": True,
        "with_glib": False,
        "with_doubleconversion": True,
        "with_freetype": True,
        "with_fontconfig": True,
        "with_icu": True,
        "with_harfbuzz": True,
        "with_libjpeg": False,
        "with_libpng": True,
        "with_sqlite3": True,
        "with_mysql": False,
        "with_pq": True,
        "with_odbc": True,
        "with_zstd": False,
        "with_brotli": True,

        "gui": True,
        "widgets": True,

        "device": None,
        "cross_compile": None,
        "sysroot": None,
        "multiconfiguration": False,
    }
    default_options.update({module: False for module in _submodules})

    short_paths = True

    _cmake = None

    _submodules_tree = None

    @property
    def _get_module_tree(self):
        if self._submodules_tree:
            return self._submodules_tree
        config = configparser.ConfigParser()
        config.read(os.path.join(self.recipe_folder, "qtmodules%s.conf" % self.version))
        self._submodules_tree = {}
        assert config.sections()
        for s in config.sections():
            section = str(s)
            assert section.startswith("submodule ")
            assert section.count('"') == 2
            modulename = section[section.find('"') + 1: section.rfind('"')]
            status = str(config.get(section, "status"))
            if status not in ["obsolete", "ignore", "additionalLibrary"]:
                self._submodules_tree[modulename] = {"status": status,
                                "path": str(config.get(section, "path")), "depends": []}
                if config.has_option(section, "depends"):
                    self._submodules_tree[modulename]["depends"] = [str(i) for i in config.get(section, "depends").split()]

        for m in self._submodules_tree:
            assert m in ["qtbase", "qtqa", "qtrepotools"] or m in self._submodules, "module %s not in self._submodules" % m

        return self._submodules_tree

    def export(self):
        self.copy("qtmodules%s.conf" % self.version)

    def config_options(self):
        if self.settings.os not in ["Linux", "FreeBSD"]:
            del self.options.with_icu
            del self.options.with_fontconfig
        if self.settings.os != "Linux":
            del self.options.qtwayland

        for m in self._submodules:
            if m not in self._get_module_tree:
                delattr(self.options, m)

        # default options
        if self.settings.os == "Windows":
            self.options.opengl = "dynamic"

    def configure(self):
        if not self.options.gui:
            del self.options.opengl
            del self.options.with_vulkan
            del self.options.with_freetype
            del self.options.with_fontconfig
            del self.options.with_harfbuzz
            del self.options.with_libjpeg
            del self.options.with_libpng

        if self.options.multiconfiguration:
            del self.settings.build_type

        def _enablemodule(mod):
            if mod != "qtbase":
                setattr(self.options, mod, True)
            for req in self._get_module_tree[mod]["depends"]:
                _enablemodule(req)

        for module in self._get_module_tree:
            if self.options.get_safe(module):
                _enablemodule(module)

    def requirements(self):
        self.requires("zlib/1.2.11")
        if self.options.openssl:
            self.requires("openssl/1.1.1k")
        if self.options.with_pcre2:
            self.requires("pcre2/10.36")
        if self.options.get_safe("with_vulkan"):
            self.requires("vulkan-loader/1.2.172")

        if self.options.with_glib:
            self.requires("glib/2.68.3")
        if self.options.with_doubleconversion and not self.options.multiconfiguration:
            # FIXME: qt seems to use vendored double-conversion even if Finddouble-conversion.cmake is found
            self.requires("double-conversion/3.1.5")
        if self.options.get_safe("with_freetype", False) and not self.options.multiconfiguration:
            self.requires("freetype/2.10.4")
        if self.options.get_safe("with_fontconfig", False):
            self.requires("fontconfig/2.13.93")
        if self.options.get_safe("with_icu", False):
            self.requires("icu/68.2")
        if self.options.get_safe("with_harfbuzz", False) and not self.options.multiconfiguration:
            self.requires("harfbuzz/2.8.1")
        if self.options.get_safe("with_libjpeg", False) and not self.options.multiconfiguration:
            if self.options.with_libjpeg == "libjpeg-turbo":
                self.requires("libjpeg-turbo/2.1.0")
            else:
                self.requires("libjpeg/9d")
        if self.options.get_safe("with_libpng", False) and not self.options.multiconfiguration:
            self.requires("libpng/1.6.37")
        if self.options.with_sqlite3 and not self.options.multiconfiguration:
            self.requires("sqlite3/3.35.5")
            self.options["sqlite3"].enable_column_metadata = True
        if self.options.get_safe("with_mysql", False):
            self.requires("libmysqlclient/8.0.17")
        if self.options.with_pq:
            self.requires("libpq/13.2")
        if self.options.with_odbc:
            if self.settings.os != "Windows":
                self.requires("odbc/2.3.9")
        if self.options.gui and self.settings.os in ["Linux", "FreeBSD"]:
            self.requires("xorg/system")
            if not tools.cross_building(self, skip_x64_x86=True):
                self.requires("xkbcommon/1.3.0")
        if self.settings.os != "Windows" and self.options.get_safe("opengl", "no") != "no":
            self.requires("opengl/system")
        if self.options.with_zstd:
            self.requires("zstd/1.5.0")
        if self.options.get_safe("qtwayland"):
            self.requires("wayland/1.19.0")
        if self.options.with_brotli:
            self.requires("brotli/1.0.9")
        if self.options.get_safe("qtimageformats"):
            self.requires("jasper/2.0.32")
            # FIXME: for some odd reason, CMake configuration fails because it improperly detects TIFF_FOUND = "False"
            # self.requires("libtiff/4.2.0")
            self.requires("libwebp/1.2.0")
            # TODO: add libmng for QMngPlugin
        if self.options.get_safe("qtopcua"):
            # TODO: use external open62541
            pass

    @property
    def _minimum_compilers_version(self):
        # Qt6 requires C++17
        return {
            "Visual Studio": "16",
            "gcc": "8",
            "clang": "9",
            "apple-clang": "11"
        }

    def validate(self):
        # C++ minimum standard required
        if self.settings.compiler.get_safe("cppstd"):
            tools.check_min_cppstd(self, 17)
        minimum_version = self._minimum_compilers_version.get(str(self.settings.compiler), False)
        if not minimum_version:
            self.output.warn("C++17 support required. Your compiler is unknown. Assuming it supports C++17.")
        elif tools.Version(self.settings.compiler.version) < minimum_version:
            raise ConanInvalidConfiguration("C++17 support required, which your compiler does not support.")

        if self.settings.os == "Android" and self.options.get_safe("opengl", "no") == "desktop":
            raise ConanInvalidConfiguration("OpenGL desktop is not supported on Android.")

        if self.settings.os != "Windows" and self.options.get_safe("opengl", "no") == "dynamic":
            raise ConanInvalidConfiguration("Dynamic OpenGL is supported only on Windows.")

        if self.options.get_safe("with_fontconfig") and not self.options.get_safe("with_freetype"):
            raise ConanInvalidConfiguration("with_fontconfig cannot be enabled if with_freetype is disabled.")

        if str(self.settings.compiler.get_safe("runtime", "")) in ["MT", "MTd", "static"] and self.options.shared:
            raise ConanInvalidConfiguration("Qt cannot be built as shared library with static runtime")

        if self.options.widgets and not self.options.gui:
            raise ConanInvalidConfiguration("widgets requires gui")

    def package_id(self):
        del self.info.options.cross_compile
        del self.info.options.sysroot
        if self.options.multiconfiguration and self.settings.compiler == "Visual Studio":
            if "MD" in self.settings.compiler.runtime:
                self.info.settings.compiler.runtime = "MD/MDd"
            else:
                self.info.settings.compiler.runtime = "MT/MTd"

    def build_requirements(self):
        self.build_requires("cmake/3.20.4")
        self.build_requires("ninja/1.10.2")
        self.build_requires("pkgconf/1.7.4")
        if self.settings.compiler == "Visual Studio":
            self.build_requires("strawberryperl/5.30.0.1")

    def source(self):
        tools.get(**self.conan_data["sources"][self.version],
                  destination="qt6", strip_root=True)

        # patching in source method because of no_copy_source attribute

        tools.replace_in_file(os.path.join("qt6", "CMakeLists.txt"),
                        "enable_testing()",
                        "include(${CMAKE_BINARY_DIR}/conanbuildinfo.cmake)\nconan_basic_setup(KEEP_RPATHS)\n"
                               "set(QT_EXTRA_INCLUDEPATHS ${CONAN_INCLUDE_DIRS})\n"
                               "set(QT_EXTRA_DEFINES ${CONAN_DEFINES})\n"
                               "set(QT_EXTRA_LIBDIRS ${CONAN_LIB_DIRS})\n"
                               "enable_testing()")

        for patch in self.conan_data.get("patches", {}).get(self.version, []):
            tools.patch(**patch)

        tools.replace_in_file(os.path.join("qt6", "qtbase", "cmake", "QtInternalTargets.cmake"),
                              "target_compile_options(PlatformCommonInternal INTERFACE -Zc:wchar_t)",
                              "target_compile_options(PlatformCommonInternal INTERFACE -Zc:wchar_t -Zc:twoPhase-)")
        for f in ["FindPostgreSQL.cmake"]:
            file = os.path.join("qt6", "qtbase", "cmake", f)
            if os.path.isfile(file):
                os.remove(file)

        # workaround QTBUG-94356
        if tools.Version(self.version) >= "6.1.1":
            tools.replace_in_file(os.path.join("qt6", "qtbase", "cmake", "FindWrapZLIB.cmake"), '"-lz"', 'ZLIB::ZLIB')
            tools.replace_in_file(os.path.join("qt6", "qtbase", "configure.cmake"),
                "set_property(TARGET ZLIB::ZLIB PROPERTY IMPORTED_GLOBAL TRUE)",
                "")

    def _xplatform(self):
        if self.settings.os == "Linux":
            if self.settings.compiler == "gcc":
                return {"x86": "linux-g++-32",
                        "armv6": "linux-arm-gnueabi-g++",
                        "armv7": "linux-arm-gnueabi-g++",
                        "armv7hf": "linux-arm-gnueabi-g++",
                        "armv8": "linux-aarch64-gnu-g++"}.get(str(self.settings.arch), "linux-g++")
            elif self.settings.compiler == "clang":
                if self.settings.arch == "x86":
                    return "linux-clang-libc++-32" if self.settings.compiler.libcxx == "libc++" else "linux-clang-32"
                elif self.settings.arch == "x86_64":
                    return "linux-clang-libc++" if self.settings.compiler.libcxx == "libc++" else "linux-clang"

        elif self.settings.os == "Macos":
            return {"clang": "macx-clang",
                    "apple-clang": "macx-clang",
                    "gcc": "macx-g++"}.get(str(self.settings.compiler))

        elif self.settings.os == "iOS":
            if self.settings.compiler == "apple-clang":
                return "macx-ios-clang"

        elif self.settings.os == "watchOS":
            if self.settings.compiler == "apple-clang":
                return "macx-watchos-clang"

        elif self.settings.os == "tvOS":
            if self.settings.compiler == "apple-clang":
                return "macx-tvos-clang"

        elif self.settings.os == "Android":
            if self.settings.compiler == "clang":
                return "android-clang"

        elif self.settings.os == "Windows":
            return {"Visual Studio": "win32-msvc",
                    "gcc": "win32-g++",
                    "clang": "win32-clang-g++"}.get(str(self.settings.compiler))

        elif self.settings.os == "WindowsStore":
            if self.settings.compiler == "Visual Studio":
                return {"14": {"armv7": "winrt-arm-msvc2015",
                               "x86": "winrt-x86-msvc2015",
                               "x86_64": "winrt-x64-msvc2015"},
                        "15": {"armv7": "winrt-arm-msvc2017",
                               "x86": "winrt-x86-msvc2017",
                               "x86_64": "winrt-x64-msvc2017"},
                        "16": {"armv7": "winrt-arm-msvc2019",
                               "x86": "winrt-x86-msvc2019",
                               "x86_64": "winrt-x64-msvc2019"}
                        }.get(str(self.settings.compiler.version)).get(str(self.settings.arch))

        elif self.settings.os == "FreeBSD":
            return {"clang": "freebsd-clang",
                    "gcc": "freebsd-g++"}.get(str(self.settings.compiler))

        elif self.settings.os == "SunOS":
            if self.settings.compiler == "sun-cc":
                if self.settings.arch == "sparc":
                    return "solaris-cc-stlport" if self.settings.compiler.libcxx == "libstlport" else "solaris-cc"
                elif self.settings.arch == "sparcv9":
                    return "solaris-cc64-stlport" if self.settings.compiler.libcxx == "libstlport" else "solaris-cc64"
            elif self.settings.compiler == "gcc":
                return {"sparc": "solaris-g++",
                        "sparcv9": "solaris-g++-64"}.get(str(self.settings.arch))
        elif self.settings.os == "Neutrino" and self.settings.compiler == "qcc":
            return {"armv8": "qnx-aarch64le-qcc",
                    "armv8.3": "qnx-aarch64le-qcc",
                    "armv7": "qnx-armle-v7-qcc",
                    "armv7hf": "qnx-armle-v7-qcc",
                    "armv7s": "qnx-armle-v7-qcc",
                    "armv7k": "qnx-armle-v7-qcc",
                    "x86": "qnx-x86-qcc",
                    "x86_64": "qnx-x86-64-qcc"}.get(str(self.settings.arch))
        elif self.settings.os == "Emscripten" and self.settings.arch == "wasm":
            return "wasm-emscripten"

        return None

    def _configure_cmake(self):
        if self._cmake:
            return self._cmake
        self._cmake = CMake(self, generator="Ninja")

        self._cmake.definitions["INSTALL_MKSPECSDIR"] = os.path.join(self.package_folder, "res", "archdatadir", "mkspecs")
        self._cmake.definitions["INSTALL_ARCHDATADIR"] = os.path.join(self.package_folder, "res", "archdatadir")
        self._cmake.definitions["INSTALL_LIBEXECDIR"] = os.path.join(self.package_folder, "bin" if self.settings.os == "Windows" else "lib")
        self._cmake.definitions["INSTALL_DATADIR"] = os.path.join(self.package_folder, "res", "datadir")
        self._cmake.definitions["INSTALL_SYSCONFDIR"] = os.path.join(self.package_folder, "res", "sysconfdir")

        self._cmake.definitions["QT_BUILD_TESTS"] = "OFF"
        self._cmake.definitions["QT_BUILD_EXAMPLES"] = "OFF"

        if self.settings.compiler == "Visual Studio":
            if self.settings.compiler.runtime == "MT" or self.settings.compiler.runtime == "MTd":
                self._cmake.definitions["FEATURE_static_runtime"] = "ON"

        if self.options.multiconfiguration:
            self._cmake.generator = "Ninja Multi-Config"
            self._cmake.definitions["CMAKE_CONFIGURATION_TYPES"] = "Release;Debug"
        self._cmake.definitions["FEATURE_optimize_size"] = ("ON" if self.settings.build_type == "MinSizeRel" else "OFF")

        for module in self._get_module_tree:
            if module != 'qtbase':
                self._cmake.definitions["BUILD_%s" % module] = ("ON" if self.options.get_safe(module) else "OFF")

        self._cmake.definitions["FEATURE_system_zlib"] = "ON"

        self._cmake.definitions["INPUT_opengl"] = self.options.get_safe("opengl", "no")

        # openSSL
        if not self.options.openssl:
            self._cmake.definitions["INPUT_openssl"] = "no"
        else:
            if self.options["openssl"].shared:
                self._cmake.definitions["INPUT_openssl"] = "runtime"
            else:
                self._cmake.definitions["INPUT_openssl"] = "linked"


        for opt, conf_arg in [("with_glib", "glib"),
                              ("with_icu", "icu"),
                              ("with_fontconfig", "fontconfig"),
                              ("with_mysql", "sql_mysql"),
                              ("with_pq", "sql_psql"),
                              ("with_odbc", "sql_odbc"),
                              ("gui", "gui"),
                              ("widgets", "widgets"),
                              ("with_zstd", "zstd"),
                              ("with_vulkan", "vulkan"),
                              ("with_brotli", "brotli")]:
            self._cmake.definitions["FEATURE_%s" % conf_arg] = ("ON" if self.options.get_safe(opt, False) else "OFF")


        for opt, conf_arg in [
                              ("with_doubleconversion", "doubleconversion"),
                              ("with_freetype", "freetype"),
                              ("with_harfbuzz", "harfbuzz"),
                              ("with_libjpeg", "jpeg"),
                              ("with_libpng", "png"),
                              ("with_sqlite3", "sqlite"),
                              ("with_pcre2", "pcre2"),]:
            if self.options.get_safe(opt, False):
                if self.options.multiconfiguration:
                    self._cmake.definitions["FEATURE_%s" % conf_arg] = "ON"
                else:
                    self._cmake.definitions["FEATURE_system_%s" % conf_arg] = "ON"
            else:
                self._cmake.definitions["FEATURE_%s" % conf_arg] = "OFF"
                self._cmake.definitions["FEATURE_system_%s" % conf_arg] = "OFF"

        if self.options.get_safe("qtimageformats"):
            self._cmake.definitions["FEATURE_tiff"] = "ON"
            self._cmake.definitions["FEATURE_system_tiff"] = "OFF" # TODO: enable when fixed
            self._cmake.definitions["FEATURE_webp"] = "ON"
            self._cmake.definitions["FEATURE_system_webp"] = "ON"
            self._cmake.definitions["FEATURE_jasper"] = "ON"
            self._cmake.definitions["FEATURE_mng"] = "OFF"

        if self.settings.os == "Macos":
            self._cmake.definitions["FEATURE_framework"] = "OFF"
        elif self.settings.os == "Android":
            self._cmake.definitions["CMAKE_ANDROID_NATIVE_API_LEVEL"] = self.settings.os.api_level
            self._cmake.definitions["ANDROID_ABI"] =  {"armv7": "armeabi-v7a",
                                           "armv8": "arm64-v8a",
                                           "x86": "x86",
                                           "x86_64": "x86_64"}.get(str(self.settings.arch))

        if self.options.sysroot:
            self._cmake.definitions["CMAKE_SYSROOT"] = self.options.sysroot

        if self.options.device:
            self._cmake.definitions["QT_QMAKE_TARGET_MKSPEC"] = os.path.join("devices", self.options.device)
        else:
            xplatform_val = self._xplatform()
            if xplatform_val:
                self._cmake.definitions["QT_QMAKE_TARGET_MKSPEC"] = xplatform_val
            else:
                self.output.warn("host not supported: %s %s %s %s" %
                                 (self.settings.os, self.settings.compiler,
                                  self.settings.compiler.version, self.settings.arch))
        if self.options.cross_compile:
            self._cmake.definitions["QT_QMAKE_DEVICE_OPTIONS"] = "CROSS_COMPILE=%s" % self.options.cross_compile

        self._cmake.definitions["FEATURE_pkg_config"] = "ON"
        if self.settings.compiler == "gcc" and self.settings.build_type == "Debug" and not self.options.shared:
            self._cmake.definitions["BUILD_WITH_PCH"]= "OFF" # disabling PCH to save disk space

        try:
            self._cmake.configure(source_folder="qt6")
        except:
            cmake_err_log = os.path.join(self.build_folder, "CMakeFiles", "CMakeError.log")
            cmake_out_log = os.path.join(self.build_folder, "CMakeFiles", "CMakeOutput.log")
            if (os.path.isfile(cmake_err_log)):
                self.output.info(tools.load(cmake_err_log))
            if (os.path.isfile(cmake_out_log)):
                self.output.info(tools.load(cmake_out_log))
            raise
        return self._cmake

    def build(self):
        for f in glob.glob("*.cmake"):
            tools.replace_in_file(f,
                "$<$<STREQUAL:$<TARGET_PROPERTY:TYPE>,SHARED_LIBRARY>:>",
                "", strict=False)
            tools.replace_in_file(f,
                "$<$<STREQUAL:$<TARGET_PROPERTY:TYPE>,MODULE_LIBRARY>:>",
                "", strict=False)
            tools.replace_in_file(f,
                "$<$<STREQUAL:$<TARGET_PROPERTY:TYPE>,EXECUTABLE>:>",
                "", strict=False)
            tools.replace_in_file(f,
                "$<$<STREQUAL:$<TARGET_PROPERTY:TYPE>,SHARED_LIBRARY>:-Wl,--export-dynamic>",
                "", strict=False)
            tools.replace_in_file(f,
                "$<$<STREQUAL:$<TARGET_PROPERTY:TYPE>,MODULE_LIBRARY>:-Wl,--export-dynamic>",
                "", strict=False)
        with tools.vcvars(self.settings) if self.settings.compiler == "Visual Studio" else tools.no_op():
            # next lines force cmake package to be in PATH before the one provided by visual studio (vcvars)
            build_env = tools.RunEnvironment(self).vars if self.settings.compiler == "Visual Studio" else {}
            build_env["MAKEFLAGS"] = "j%d" % tools.cpu_count()
            build_env["PKG_CONFIG_PATH"] = [self.build_folder]
            if self.settings.os == "Windows":
                if not "PATH" in build_env:
                    build_env["PATH"] = []
                build_env["PATH"].append(os.path.join(self.source_folder, "qt6", "gnuwin32", "bin"))
            if self.settings.compiler == "Visual Studio":
                # this avoids cmake using gcc from strawberryperl
                build_env["CC"] = "cl"
                build_env["CXX"] = "cl"
            with tools.environment_append(build_env):

                if tools.os_info.is_macos:
                    open(".qmake.stash" , "w").close()
                    open(".qmake.super" , "w").close()

                cmake = self._configure_cmake()
                if tools.os_info.is_macos:
                    with open("bash_env", "w") as f:
                        f.write('export DYLD_LIBRARY_PATH="%s"' % ":".join(RunEnvironment(self).vars["DYLD_LIBRARY_PATH"]))
                with tools.environment_append({
                    "BASH_ENV": os.path.abspath("bash_env")
                }) if tools.os_info.is_macos else tools.no_op():
                    with tools.run_environment(self):
                        cmake.build()

    @property
    def _cmake_executables_file(self):
        return os.path.join("lib", "cmake", "Qt6Core", "conan_qt_executables_variables.cmake")

    def _cmake_qt6_private_file(self, module):
        return os.path.join("lib", "cmake", "Qt6{0}".format(module), "conan_qt_qt6_{0}private.cmake".format(module.lower()))

    def package(self):
        cmake = self._configure_cmake()
        cmake.install()
        with open(os.path.join(self.package_folder, "bin", "qt.conf"), "w") as f:
            f.write(qt.content_template("..", "res", self.settings.os))
        self.copy("*LICENSE*", src="qt6/", dst="licenses")
        for module in self._get_module_tree:
            if module != "qtbase" and not self.options.get_safe(module):
                tools.rmdir(os.path.join(self.package_folder, "licenses", module))
        tools.rmdir(os.path.join(self.package_folder, "lib", "pkgconfig"))
        for mask in ["Find*.cmake", "*Config.cmake", "*-config.cmake"]:
            tools.remove_files_by_mask(self.package_folder, mask)
        tools.remove_files_by_mask(os.path.join(self.package_folder, "lib"), "*.la*")
        tools.remove_files_by_mask(self.package_folder, "*.pdb*")
        os.remove(os.path.join(self.package_folder, "bin", "qt-cmake-private-install.cmake"))

        for m in os.listdir(os.path.join(self.package_folder, "lib", "cmake")):
            module = os.path.join(self.package_folder, "lib", "cmake", m, "%sMacros.cmake" % m)
            if not os.path.isfile(module):
                tools.rmdir(os.path.join(self.package_folder, "lib", "cmake", m))

        extension = ""
        if self.settings.os == "Windows":
            extension = ".exe"
        filecontents = "set(QT_CMAKE_EXPORT_NAMESPACE Qt6)\n"
        ver = tools.Version(self.version)
        filecontents += "set(QT_VERSION_MAJOR %s)\n" % ver.major
        filecontents += "set(QT_VERSION_MINOR %s)\n" % ver.minor
        filecontents += "set(QT_VERSION_PATCH %s)\n" % ver.patch
        targets = ["moc", "rcc", "tracegen", "cmake_automoc_parser", "qlalr", "qmake"]
        targets.extend(["qdbuscpp2xml", "qdbusxml2cpp"])
        if self.options.gui:
            targets.append("qvkgen")
        if self.options.widgets:
            targets.append("uic")
        if self.options.qttools:
            targets.extend(["qhelpgenerator", "qtattributionsscanner", "windeployqt"])
            targets.extend(["lconvert", "lprodump", "lrelease", "lrelease-pro", "lupdate", "lupdate-pro"])
        if self.options.qtshadertools:
            targets.append("qsb")
        if self.options.qtdeclarative:
            targets.extend(["qmltyperegistrar", "qmlcachegen", "qmllint", "qmlimportscanner"])
            targets.extend(["qmlformat", "qml", "qmlprofiler", "qmlpreview", "qmltestrunner"])
        for target in targets:
            exe_path = None
            for path_ in ["bin/{0}{1}".format(target, extension),
                          "lib/{0}{1}".format(target, extension)]:
                if os.path.isfile(os.path.join(self.package_folder, path_)):
                    exe_path = path_
                    break
            if not exe_path:
                self.output.warn("Could not find path to {0}{1}".format(target, extension))
            filecontents += textwrap.dedent("""\
                if(NOT TARGET ${{QT_CMAKE_EXPORT_NAMESPACE}}::{0})
                    add_executable(${{QT_CMAKE_EXPORT_NAMESPACE}}::{0} IMPORTED)
                    set_target_properties(${{QT_CMAKE_EXPORT_NAMESPACE}}::{0} PROPERTIES IMPORTED_LOCATION ${{CMAKE_CURRENT_LIST_DIR}}/../../../{1})
                endif()
                """.format(target, exe_path))
        tools.save(os.path.join(self.package_folder, self._cmake_executables_file), filecontents)

        def _create_private_module(module, dependencies=[]):
            dependencies_string = ';'.join('Qt6::%s' % dependency for dependency in dependencies)
            contents = textwrap.dedent("""\
            if(NOT TARGET Qt6::{0}Private)
                add_library(Qt6::{0}Private INTERFACE IMPORTED)

                set_target_properties(Qt6::{0}Private PROPERTIES
                    INTERFACE_INCLUDE_DIRECTORIES "${{CMAKE_CURRENT_LIST_DIR}}/../../../include/Qt{0}/{1};${{CMAKE_CURRENT_LIST_DIR}}/../../../include/Qt{0}/{1}/Qt{0}"
                    INTERFACE_LINK_LIBRARIES "{2}"
                )

                add_library(Qt::{0}Private INTERFACE IMPORTED)
                set_target_properties(Qt::{0}Private PROPERTIES
                    INTERFACE_LINK_LIBRARIES "Qt6::{0}Private"
                    _qt_is_versionless_target "TRUE"
                )
            endif()""".format(module, self.version, dependencies_string))

            tools.save(os.path.join(self.package_folder, self._cmake_qt6_private_file(module)), contents)

        _create_private_module("Core", ["Core"])

        if self.options.qtdeclarative:
            _create_private_module("Qml", ["CorePrivate", "Qml"])

    def package_info(self):
        self.cpp_info.names["cmake_find_package"] = "Qt6"
        self.cpp_info.names["cmake_find_package_multi"] = "Qt6"

        libsuffix = ""
        if self.settings.build_type == "Debug":
            if self.settings.os == "Windows":
                libsuffix = "d"
            if tools.is_apple_os(self.settings.os):
                libsuffix = "_debug"

        def _get_corrected_reqs(requires):
            reqs = []
            for r in requires:
                reqs.append(r if "::" in r else "qt%s" % r)
            return reqs

        def _create_module(module, requires, defines, system_libs, frameworks, header_only=False):
            componentname = "qt%s" % module
            assert componentname not in self.cpp_info.components, "Module %s already present in self.cpp_info.components" % module
            self.cpp_info.components[componentname].names["cmake_find_package"] = module
            self.cpp_info.components[componentname].names["cmake_find_package_multi"] = module
            if not header_only:
                self.cpp_info.components[componentname].libs = ["Qt6%s%s" % (module, libsuffix)]
            self.cpp_info.components[componentname].includedirs = ["include", os.path.join("include", "Qt%s" % module)]
            self.cpp_info.components[componentname].defines = ["QT_%s_LIB" % module.upper()] + defines
            self.cpp_info.components[componentname].requires = _get_corrected_reqs(requires)
            self.cpp_info.components[componentname].system_libs = system_libs
            self.cpp_info.components[componentname].frameworks = frameworks

        def _create_plugin(pluginname, libs, type, requires, system_libs, frameworks):
            componentname = "qt%s" % pluginname
            assert componentname not in self.cpp_info.components, "Plugin %s already present in self.cpp_info.components" % pluginname
            self.cpp_info.components[componentname].names["cmake_find_package"] = pluginname
            self.cpp_info.components[componentname].names["cmake_find_package_multi"] = pluginname
            if not self.options.shared:
                self.cpp_info.components[componentname].libs = ["{}{}".format(libname, libsuffix) for libname in libs]
            self.cpp_info.components[componentname].libdirs = [os.path.join("res", "archdatadir", "plugins", type)]
            self.cpp_info.components[componentname].includedirs = []
            self.cpp_info.components[componentname].requires = _get_corrected_reqs(requires)
            self.cpp_info.components[componentname].system_libs = system_libs
            self.cpp_info.components[componentname].frameworks = frameworks

        modules = self._qtbase_components["modules"]
        plugins = self._qtbase_components["plugins"]
        if self.options.qtsvg:
            modules.update(self._qtsvg_components["modules"])
            plugins.update(self._qtsvg_components["plugins"])
        if self.options.qtdeclarative:
            modules.update(self._qtdeclarative_components["modules"])
            plugins.update(self._qtdeclarative_components["plugins"])
        if self.options.get_safe("qtactiveqt"):
            modules.update(self._qtactiveqt_components["modules"])
            plugins.update(self._qtactiveqt_components["plugins"])
        if self.options.qttools:
            modules.update(self._qttools_components["modules"])
            plugins.update(self._qttools_components["plugins"])
        if self.options.get_safe("qtwayland"):
            modules.update(self._qtwayland_components["modules"])
            plugins.update(self._qtwayland_components["plugins"])
        if self.options.get_safe("qt3d"):
            modules.update(self._qt3d_components["modules"])
            plugins.update(self._qt3d_components["plugins"])
        if self.options.get_safe("qtimageformats"):
            modules.update(self._qtimageformats_components["modules"])
            plugins.update(self._qtimageformats_components["plugins"])
        if self.options.qtquickcontrols2:
            modules.update(self._qtquickcontrols2_components["modules"])
            plugins.update(self._qtquickcontrols2_components["plugins"])
        if self.options.get_safe("qtcharts"):
            modules.update(self._qtcharts_components["modules"])
            plugins.update(self._qtcharts_components["plugins"])
        if self.options.get_safe("qtdatavis3d"):
            modules.update(self._qtdatavis3d_components["modules"])
            plugins.update(self._qtdatavis3d_components["plugins"])
        if self.options.get_safe("qtvirtualkeyboard"):
            modules.update(self._qtvirtualkeyboard_components["modules"])
            plugins.update(self._qtvirtualkeyboard_components["plugins"])
        if self.options.get_safe("qtscxml"):
            modules.update(self._qtscxml_components["modules"])
            plugins.update(self._qtscxml_components["plugins"])
        if self.options.get_safe("qtnetworkauth"):
            modules.update(self._qtnetworkauth_components["modules"])
            plugins.update(self._qtnetworkauth_components["plugins"])
        if self.options.get_safe("qtlottie"):
            modules.update(self._qtlottie_components["modules"])
            plugins.update(self._qtlottie_components["plugins"])
        if self.options.qtquick3d:
            modules.update(self._qtquick3d_components["modules"])
            plugins.update(self._qtquick3d_components["plugins"])
        if self.options.qtshadertools:
            modules.update(self._qtshadertools_components["modules"])
            plugins.update(self._qtshadertools_components["plugins"])
        if self.options.qt5compat:
            modules.update(self._qt5compat_components["modules"])
            plugins.update(self._qt5compat_components["plugins"])
        if self.options.get_safe("qtcoap"):
            modules.update(self._qtcoap_components["modules"])
            plugins.update(self._qtcoap_components["plugins"])
        if self.options.get_safe("qtmqtt"):
            modules.update(self._qtmqtt_components["modules"])
            plugins.update(self._qtmqtt_components["plugins"])
        if self.options.get_safe("qtopcua"):
            modules.update(self._qtopcua_components["modules"])
            plugins.update(self._qtopcua_components["plugins"])

        # Create modules and plugins
        for module, properties in modules.items():
            requires = properties.get("requires", [])
            defines = properties.get("defines", [])
            system_libs = properties.get("system_libs", [])
            frameworks = properties.get("frameworks", [])
            header_only = properties.get("header_only", False)
            _create_module(module, requires, defines, system_libs, frameworks, header_only=header_only)
        for pluginname, properties in plugins.items():
            libs = properties.get("libs", [])
            type = properties.get("type", "")
            requires = properties.get("requires", [])
            system_libs = properties.get("system_libs", [])
            frameworks = properties.get("frameworks", [])
            _create_plugin(pluginname, libs, type, requires, system_libs, frameworks)

        if tools.Version(self.version) < "6.1.0":
            self.cpp_info.components["qtCore"].libs.append("Qt6Core_qobject%s" % libsuffix)

        if self.options.qtdeclarative:
            self.cpp_info.components["qtQml"].build_modules["cmake_find_package"].append(self._cmake_qt6_private_file("Qml"))
            self.cpp_info.components["qtQml"].build_modules["cmake_find_package_multi"].append(self._cmake_qt6_private_file("Qml"))
            self.cpp_info.components["qtQmlImportScanner"].names["cmake_find_package"] = "QmlImportScanner" # this is an alias for Qml and there to integrate with existing consumers
            self.cpp_info.components["qtQmlImportScanner"].names["cmake_find_package_multi"] = "QmlImportScanner"
            self.cpp_info.components["qtQmlImportScanner"].requires = _get_corrected_reqs(["Qml"])

        if self.settings.os != "Windows":
            self.cpp_info.components["qtCore"].cxxflags.append("-fPIC")

        self.cpp_info.components["qtCore"].builddirs.append(os.path.join("res", "archdatadir", "bin"))
        self.cpp_info.components["qtCore"].build_modules["cmake_find_package"].append(self._cmake_executables_file)
        self.cpp_info.components["qtCore"].build_modules["cmake_find_package_multi"].append(self._cmake_executables_file)
        self.cpp_info.components["qtCore"].build_modules["cmake_find_package"].append(self._cmake_qt6_private_file("Core"))
        self.cpp_info.components["qtCore"].build_modules["cmake_find_package_multi"].append(self._cmake_qt6_private_file("Core"))

        for m in os.listdir(os.path.join("lib", "cmake")):
            module = os.path.join("lib", "cmake", m, "%sMacros.cmake" % m)
            component_name = m.replace("Qt6", "qt")
            self.cpp_info.components[component_name].build_modules["cmake_find_package"].append(module)
            self.cpp_info.components[component_name].build_modules["cmake_find_package_multi"].append(module)
            self.cpp_info.components[component_name].builddirs.append(os.path.join("lib", "cmake", m))

        objects_dirs = glob.glob(os.path.join(self.package_folder, "lib", "objects-*/"))
        for object_dir in objects_dirs:
            for m in os.listdir(object_dir):
                submodules_dir = os.path.join(object_dir, m)
                component = "qt" + m[:m.find("_")]
                for sub_dir in os.listdir(submodules_dir):
                    submodule_dir = os.path.join(submodules_dir, sub_dir)
                    obj_files = [os.path.join(submodule_dir, file) for file in os.listdir(submodule_dir)]
                    self.cpp_info.components[component].exelinkflags.extend(obj_files)
                    self.cpp_info.components[component].sharedlinkflags.extend(obj_files)

    @property
    def _qtbase_components(self):
        def pcre2():
            return ["pcre2::pcre2"] if self.options.with_pcre2 else []

        def doubleconversion():
            return ["double-conversion::double-conversion"] if self.options.with_doubleconversion and not self.options.multiconfiguration else []

        def glib():
            return ["glib::glib"] if self.options.with_glib else []

        def icu():
            return ["icu::icu"] if self.options.get_safe("with_icu") else []

        def zstd():
            return ["zstd::zstd"] if self.options.with_zstd else []

        def freetype():
            return ["freetype::freetype"] if self.options.with_freetype else []

        def png():
            return ["libpng::libpng"] if self.options.with_libpng else []

        def fontconfig():
            return ["fontconfig::fontconfig"] if self.options.get_safe("with_fontconfig") else []

        def xorg():
            xorg = []
            if self.settings.os in ["Linux", "FreeBSD"]:
                xorg.append("xorg::xorg")
                if not tools.cross_building(self, skip_x64_x86=True):
                    xorg.append("xkbcommon::xkbcommon")
            return xorg

        def opengl():
            return ["opengl::opengl"] if self.settings.os != "Windows" and self.options.get_safe("opengl", "no") != "no" else []

        def harfbuzz():
            return ["harfbuzz::harfbuzz"] if self.options.with_harfbuzz else []

        def jpeg():
            if self.options.with_libjpeg == "libjpeg-turbo":
                return ["libjpeg-turbo::libjpeg-turbo"]
            elif self.options.with_libjpeg == "libjpeg":
                return ["libjpeg::libjpeg"]
            return []

        def vulkan():
            return ["vulkan-loader::vulkan-loader"] if self.options.get_safe("with_vulkan") else []

        def openssl():
            return ["openssl::openssl"] if self.options.openssl else []

        def brotli():
            return ["brotli::brotli"] if self.options.with_brotli else []

        modules = {}
        plugins = {}

        # TODO: Entrypoint library for Windows and iOS
        # TODO: add missing modules: DeviceDiscoverySupport, FbSupport

        core_system_libs = []
        core_frameworks = []
        if self.settings.os == "Windows":
            core_system_libs.extend(["advapi32", "netapi32", "ole32", "shell32", "user32",
                                     "uuid", "version", "winmm", "ws2_32", "mpr", "userenv"])
        elif self.settings.os in ["Linux", "FreeBSD"]:
            core_system_libs.extend(["m", "dl", "pthread"])
        elif tools.is_apple_os(self.settings.os):
            core_frameworks.extend(["CoreFoundation", "Foundation"])
            if self.settings.os == "Macos":
                core_frameworks.extend(["AppKit", "ApplicationServices", "CoreServices",
                                        "Security", "DiskArbitration", "IOKit"])
            elif self.settings.os in ["iOS", "tvOS"]:
                core_frameworks.append("UIKit")
            elif self.settings.os == "watchOS":
                core_frameworks.append("WatchKit")

        network_system_libs = []
        network_frameworks = []
        if self.settings.os == "Windows":
            network_system_libs.extend(["advapi32", "dnsapi", "iphlpapi"])
            # TODO: what is the condition?
            # network_system_libs.extend(["Crypt32", "Secur32", "bcrypt", "ncrypt"])
        elif self.settings.os in ["Linux", "FreeBSD"]:
            network_system_libs.extend(["dl"])
        elif tools.is_apple_os(self.settings.os):
            if self.settings.os == "Macos":
                network_frameworks.extend(["CoreServices", "GSS"])
            if self.settings.os in ["Macos", "iOS"]:
                network_frameworks.append("SystemConfiguration")

        dbus_system_libs = []
        if self.settings.os == "Windows":
            dbus_system_libs.extend(["advapi32", "netapi32", "user32", "ws2_32"])

        test_frameworks = []
        if tools.is_apple_os(self.settings.os):
            test_frameworks.append("Security")
            if self.settings.os == "Macos":
                test_frameworks.extend(["AppKit", "ApplicationServices", "Foundation", "IOKit"])

        modules.update({
            "Core": {"requires": ["zlib::zlib"] + pcre2() + doubleconversion() + glib() + icu() + zstd(), "system_libs": core_system_libs, "frameworks": core_frameworks},
            "Concurrent": {"requires": ["Core"]},
            "Sql": {"requires": ["Core"]},
            "Network": {"requires": ["Core", "zlib::zlib"] + openssl() + brotli() + zstd(), "system_libs": network_system_libs, "frameworks": network_frameworks},
            "Xml": {"requires": ["Core"]},
            "DBus": {"requires": ["Core"], "system_libs": dbus_system_libs},
            "Test": {"requires": ["Core"], "frameworks": test_frameworks},
        })

        if self.options.gui:
            # Gui
            gui_system_libs = []
            gui_frameworks = []
            if self.settings.os == "Windows":
                gui_system_libs.extend(["advapi32", "gdi32", "ole32", "shell32", "user32",
                                        "d3d11", "dxgi", "dxguid", "d2d1", "dwrite"])
                if self.settings.compiler == "gcc":
                    gui_system_libs.append("uuid")
            elif self.settings.os in ["Linux", "FreeBSD"]:
                gui_system_libs.append("dl")
            elif tools.is_apple_os(self.settings.os):
                gui_frameworks.extend(["CoreServices", "CoreGraphics", "CoreText", "Foundation", "ImageIO"])
                if self.settings.os == "Macos":
                    gui_frameworks.extend(["AppKit", "Carbon"])
                if self.settings.os in ["Macos", "iOS"]:
                    gui_frameworks.append("Metal")
                if self.settings.os != "Macos":
                    gui_frameworks.append("UIKit")
            modules.update({
                "Gui": {
                    "requires": ["Core", "DBus", "zlib::zlib"] + freetype() + png() + fontconfig() +
                                 xorg() + opengl() + harfbuzz() + jpeg() + vulkan() + glib(),
                    "system_libs": gui_system_libs,
                    "frameworks": gui_frameworks,
                }
            })
            # OpenGL
            if self.options.get_safe("opengl", "no") != "no":
                modules.update({"OpenGL": {"requires": ["Core", "Gui"] + vulkan()}})

            # platforms plugins
            if self.settings.os != "Android":
                plugins.update({
                    "QMinimalIntegrationPlugin": {
                        "libs": ["qminimal"],
                        "type": "platforms",
                        "requires": ["Core", "Gui"] + freetype(),
                    }
                })
                if self.options.get_safe("with_fontconfig"):
                    plugins.update({
                        "QOffscreenIntegrationPlugin": {
                            "libs": ["qoffscreen"],
                            "type": "platforms",
                            "requires": ["Core", "Gui"] + xorg(),
                        }
                    })
            if self.settings.os == "Android":
                # TODO: should link to EGL also
                plugins.update({
                    "QAndroidIntegrationPlugin": {
                        "libs": ["qtforandroid"],
                        "type": "platforms",
                        "requires": ["Core", "Gui"],
                        "system_libs": ["android", "jnigraphics"],
                    }
                })
            elif self.settings.os in ["Linux", "FreeBSD"]:
                plugins.update({
                    "QXcbIntegrationPlugin": {
                        "libs": ["qxcb"],
                        "type": "platforms",
                        "requires": ["Core", "Gui"],
                    }
                })
                # TODO: QXcbEglIntegrationPlugin and QXcbGlxIntegrationPlugin?
            elif self.settings.os in ["iOS", "tvOS"]:
                ios_int_plugin_frameworks = ["AudioToolbox", "Foundation", "Metal", "QuartzCore", "UIKit"]
                if self.settings.os != "tvOS":
                    ios_int_plugin_frameworks.append("AssetsLibrary")
                plugins.update({
                    "QIOSIntegrationPlugin": {
                        "libs": ["qios"],
                        "type": "platforms",
                        "requires": ["Core", "Gui"] + opengl(),
                        "frameworks": ios_int_plugin_frameworks,
                    }
                })
            elif self.settings.os == "Macos":
                plugins.update({
                    "QCocoaIntegrationPlugin": {
                        "libs": ["qcocoa"],
                        "type": "platforms",
                        "requires": ["Core", "Gui"],
                        "frameworks": ["AppKit", "Carbon", "CoreServices", "CoreVideo",
                                       "IOKit", "IOSurface", "Metal", "QuartzCore"],
                    }
                })
            elif self.settings.os == "Windows":
                win_int_plugin_reqs = ["Core", "Gui"]
                win_int_plugin_system_libs = ["advapi32", "dwmapi", "gdi32", "imm32", "ole32", "oleaut32",
                                              "shell32", "shlwapi", "user32", "winmm", "winspool", "wtsapi32"]
                if self.options.get_safe("opengl", "no") != "no":
                    win_int_plugin_reqs.append("OpenGL")
                    if self.options.get_safe("opengl", "no") != "dynamic":
                        win_int_plugin_system_libs.append("opengl32")
                if self.settings.compiler == "gcc":
                    win_int_plugin_system_libs.append("uuid")
                plugins.update({
                    "QWindowsIntegrationPlugin": {
                        "libs": ["qwindows"],
                        "type": "platforms",
                        "requires": win_int_plugin_reqs,
                        "system_libs": win_int_plugin_system_libs,
                    }
                })
                win_d2d_int_plugin_reqs = ["Core", "Gui"]
                win_d2d_int_plugin_system_libs = ["advapi32", "d2d1", "d3d11", "dwmapi", "dwrite", "dxgi",
                                                  "dxguid", "gdi32", "imm32", "ole32", "oleaut32", "shell32",
                                                  "shlwapi", "user32", "version", "winmm", "winspool", "wtsapi32"]
                if self.options.get_safe("opengl", "no") != "no":
                    win_d2d_int_plugin_reqs.append("OpenGL")
                    if self.options.get_safe("opengl", "no") != "dynamic":
                        win_d2d_int_plugin_system_libs.append("opengl32")
                if self.settings.compiler == "gcc":
                    win_d2d_int_plugin_system_libs.append("uuid")
                plugins.update({
                    "QWindowsDirect2DIntegrationPlugin": {
                        "libs": ["qdirect2d"],
                        "type": "platforms",
                        "requires": win_d2d_int_plugin_reqs,
                        "system_libs": win_d2d_int_plugin_system_libs,
                    }
                })

            # imageformats plugins
            plugins.update({
                "QICOPlugin": {
                    "libs": ["qico"],
                    "type": "imageformats",
                    "requires": ["Core", "Gui"],
                }
            })
            if bool(self.options.with_libjpeg):
                plugins.update({
                    "QJpegPlugin": {
                        "libs": ["qjpeg"],
                        "type": "imageformats",
                        "requires": ["Core", "Gui"] + jpeg(),
                    }
                })
            plugins.update({
                "QGifPlugin": {
                    "libs": ["qgif"],
                    "type": "imageformats",
                    "requires": ["Core", "Gui"],
                }
            })

            # generic plugins
            if self.settings.os != "Android":
                plugins.update({
                    "QTuioTouchPlugin": {
                        "libs": ["qtuiotouchplugin"],
                        "type": "generic",
                        "requires": ["Core", "Gui", "Network"],
                    }
                })
                # TODO: there are more optional generic plugins but don't seem to be enabled by recipe

            if self.options.widgets:
                ## Widgets
                widgets_system_libs = []
                widgets_frameworks = []
                if self.settings.os == "Windows":
                    widgets_system_libs.extend(["dwmapi", "shell32", "uxtheme"])
                elif self.settings.os == "Macos":
                    widgets_frameworks.append("AppKit")
                modules.update({
                    "Widgets": {
                        "requires": ["Core", "Gui"],
                        "system_libs": widgets_system_libs,
                        "frameworks": widgets_frameworks,
                    }
                })

                # styles plugins
                if self.settings.os == "Android":
                    plugins.update({
                        "QAndroidStylePlugin": {
                            "libs": ["qandroidstyle"],
                            "type": "styles",
                            "requires": ["Core", "Gui", "Widgets"],
                        }
                    })
                elif self.settings.os == "Macos":
                    plugins.update({
                        "QMacStylePlugin": {
                            "libs": ["qmacstyle"],
                            "type": "styles",
                            "requires": ["Core", "Gui", "Widgets"],
                            "frameworks": ["AppKit"]
                        }
                    })
                elif self.settings.os == "Windows":
                    plugins.update({
                        "QWindowsVistaStylePlugin": {
                            "libs": ["qwindowsvistastyle"],
                            "type": "styles",
                            "requires": ["Core", "Gui", "Widgets"],
                            "system_libs": ["gdi32", "user32", "uxtheme"]
                        }
                    })

                # PrintSupport
                printsupport_system_libs = []
                printsupport_frameworks = []
                if self.settings.os == "Windows":
                    printsupport_system_libs.extend(["gdi32", "user32", "comdlg32", "winspool"])
                elif self.settings.os == "Macos":
                    printsupport_frameworks.extend(["ApplicationServices", "AppKit"])
                    printsupport_system_libs.append("cups")
                modules.update({
                    "PrintSupport": {
                        "requires": ["Core", "Gui", "Widgets"],
                        "system_libs": printsupport_system_libs,
                        "frameworks": printsupport_system_libs,
                    }
                })

                # TODO: printsupport plugins (QCupsPrinterSupportPlugin only if cups found on Unix systems but not Apple)

                # OpenGLWidgets
                if self.options.get_safe("opengl", "no") != "no":
                    modules.update({"OpenGLWidgets": {"requires": ["OpenGL", "Widgets"]}})

        # sql plugins
        if self.options.with_sqlite3:
            plugins.update({
                "QSQLiteDriverPlugin": {
                    "libs": ["qsqlite"],
                    "type": "sqldrivers",
                    "requires": ["Core", "Sql", "sqlite3::sqlite3"],
                }
            })
        if self.options.with_pq:
            plugins.update({
                "QPSQLDriverPlugin": {
                    "libs": ["qsqlpsql"],
                    "type": "sqldrivers",
                    "requires": ["Core", "Sql", "libpq::libpq"],
                }
            })
        if self.options.with_odbc:
            odbcdriverplugin_requires = ["Core", "Sql"]
            odbcdriverplugin_system_libs = []
            if self.settings.os == "Windows":
                odbcdriverplugin_system_libs.append("odbc32")
            else:
                odbcdriverplugin_requires.append("odbc::odbc")
            plugins.update({
                "QODBCDriverPlugin": {
                    "libs": ["qsqlodbc"],
                    "type": "sqldrivers",
                    "requires": odbcdriverplugin_requires,
                    "system_libs": odbcdriverplugin_system_libs,
                }
            })

        # network plugins
        # TODO: plugin name / type / libs are different in dev branch, they may change in 6.2.0
        if tools.Version(self.version) >= "6.1.0":
            if self.settings.os == "Windows":
                plugins.update({
                    "QNetworkListManagerNetworkInformationBackend": {
                        "libs": ["networklistmanagernetworkinformationbackend"],
                        "type": "networkinformationbackends",
                        "requires": ["Network"],
                    }
                })
            elif self.settings.os in ["Linux", "FreeBSD"]:
                plugins.update({
                    "QNetworkManagerNetworkInformationBackend": {
                        "libs": ["networkmanagernetworkinformationbackend"],
                        "type": "networkinformationbackends",
                        "requires": ["DBus", "Network"],
                    }
                })
            elif tools.is_apple_os(self.settings.os):
                plugins.update({
                    "QSCNetworkReachabilityNetworkInformationBackend": {
                        "libs": ["scnetworkreachabilitynetworkinformationbackend"],
                        "type": "networkinformationbackends",
                        "requires": ["Network"],
                        "frameworks": ["SystemConfiguration"],
                    }
                })
            elif self.settings.os == "Android":
                plugins.update({
                    "QAndroidNetworkInformationBackend": {
                        "libs": ["androidnetworkinformationbackend"],
                        "type": "networkinformationbackends",
                        "requires": ["Network"],
                    }
                })

        # TODO: tls plugins (in dev branch only, maybe for 6.2.0?)

        return {"modules": modules, "plugins": plugins}

    @property
    def _qtsvg_components(self):
        modules = {}
        plugins = {}
        if self.options.gui:
            modules.update({"Svg": {"requires": ["Gui"]}})
            plugins.update({
                "QSvgIconPlugin": {"libs": ["qsvgicon"], "type": "iconengines", "requires": ["Core", "Gui", "Svg"]},
                "QSvgPlugin": {"libs": ["qsvg"], "type": "imageformats", "requires": ["Core", "Gui", "Svg"]},
            })
            if self.options.widgets:
                modules.update({"SvgWidgets": {"requires": ["Core", "Gui", "Svg", "Widgets"]}})
        return {"modules": modules, "plugins": plugins}

    @property
    def _qtdeclarative_components(self):
        modules = {}
        plugins = {}

        qml_system_libs = []
        if self.settings.os == "Windows":
            qml_system_libs.append("shell32")
        elif self.settings.os in ["Linux", "FreeBSD"] and not self.options.shared:
            qml_system_libs.append("rt")
        modules.update({
            "Qml": {"requires": ["Core", "Network"], "system_libs": qml_system_libs},
            "QmlModels": {"requires": ["Core", "Qml"]},
            "QmlWorkerScript": {"requires": ["Core", "Qml"]},
            "PacketProtocol": {"requires": ["Core"]},
            "QmlDevTools": {"requires": ["Core"]},
            "QmlCompiler": {"requires": ["Core", "QmlDevTools"]},
            "QmlDebug": {"requires": ["Core", "Network", "PacketProtocol", "Qml"]},
        })
        plugins.update({
            "QQmlNativeDebugConnectorFactory": {"libs": ["qmldbg_native"], "type": "qmltooling", "requires": ["Core", "PacketProtocol", "Qml"]},
            "QDebugMessageServiceFactory": {"libs": ["qmldbg_messages"], "type": "qmltooling", "requires": ["Core", "PacketProtocol", "Qml"]},
            "QQmlProfilerServiceFactory": {"libs": ["qmldbg_profiler"], "type": "qmltooling", "requires": ["Core", "PacketProtocol", "Qml"]},
            "QQmlDebuggerServiceFactory": {"libs": ["qmldbg_debugger"], "type": "qmltooling", "requires": ["Core", "PacketProtocol", "Qml"]},
            "QQmlNativeDebugServiceFactory": {"libs": ["qmldbg_nativedebugger"], "type": "qmltooling", "requires": ["Core", "PacketProtocol", "Qml"]},
            "QQmlDebugServerFactory": {"libs": ["qmldbg_server"], "type": "qmltooling", "requires": ["PacketProtocol", "Qml"]},
            "QTcpServerConnectionFactory": {"libs": ["qmldbg_tcp"], "type": "qmltooling", "requires": ["Network", "Qml"]},
            "QLocalClientConnectionFactory": {"libs": ["qmldbg_local"], "type": "qmltooling", "requires": ["Qml"]},
        })
        if tools.Version(self.version) >= "6.1.0":
            modules.update({
                "QmlLocalStorage": {"requires": ["Core", "Qml", "Sql"]},
                "LabsSettings": {"requires": ["Core", "Qml"]},
                "LabsQmlModels": {"requires": ["Core", "Qml"]},
                "LabsFolderListModel": {"requires": ["Qml", "QmlModels"]},
                "QmlDom": {"requires": ["Core", "QmlDevTools"]},
            })
        if self.options.gui:
            quick_requires = ["Core", "Gui", "Qml", "QmlModels", "Network"]
            if self.options.get_safe("opengl", "no") != "no":
                quick_requires.append("OpenGL")
            quick_system_libs = ["user32"] if self.settings.os == "Windows" else []
            modules.update({
                "Quick": {"requires": quick_requires, "system_libs": quick_system_libs},
                "QuickShapes": {"requires": ["Core", "Gui", "Qml", "Quick"]},
                "QuickTest": {"requires": ["Core", "Gui", "Qml", "Quick", "Test"]},
                "QuickParticles": {"requires": ["Core", "Gui", "Qml", "Quick"]},
            })
            plugins.update({
                "QQmlInspectorServiceFactory": {"libs": ["qmldbg_inspector"], "type": "qmltooling", "requires": ["Core", "Gui", "PacketProtocol", "Qml", "Quick"]},
                "QQuickProfilerAdapterFactory": {"libs": ["qmldbg_quickprofiler"], "type": "qmltooling", "requires": ["Core", "Gui", "PacketProtocol", "Qml", "Quick"]},
                "QQmlPreviewServiceFactory": {"libs": ["qmldbg_preview"], "type": "qmltooling", "requires": ["Core", "Gui", "Network", "PacketProtocol", "Qml", "Quick"]},
            })
            if tools.Version(self.version) >= "6.1.0":
                modules.update({
                    "QuickLayouts": {"requires": ["Core", "Gui", "Qml", "Quick"]},
                    "LabsAnimation": {"requires": ["Qml", "Quick"]},
                    "LabsWavefrontMesh": {"requires": ["Core", "Gui", "Quick"]},
                    "LabsSharedImage": {"requires": ["Core", "Gui", "Quick"]},
                })
            if self.options.widgets:
                quickwidgets_requires = ["Core", "Gui", "Qml", "Quick", "Widgets"]
                if self.options.get_safe("opengl", "no") != "no":
                    quickwidgets_requires.append("OpenGL")
                modules.update({"QuickWidgets": {"requires": quickwidgets_requires}})

        return {"modules": modules, "plugins": plugins}

    @property
    def _qtactiveqt_components(self):
        modules = {}
        if self.settings.os == "Windows" and self.options.gui and self.options.widgets:
            axbase_system_libs = ["advapi32", "gdi32", "ole32", "oleaut32", "user32"]
            if self.settings.compiler == "gcc":
                axbase_system_libs.append("uuid")
            modules.update({
                "AxBase": {"requires": ["Core", "Gui", "Widgets"], "system_libs": axbase_system_libs},
                "AxServer": {"requires": ["AxBase", "Core", "Gui", "Widgets"], "defines": ["QAXSERVER"], "system_libs": ["shell32"]},
                "AxContainer": {"requires": ["AxBase", "Core", "Gui", "Widgets"]},
            })
        return {"modules": modules, "plugins": {}}

    @property
    def _qttools_components(self):
        modules = {}
        plugins = {}
        if self.options.gui and self.options.widgets:
            uitools_requires = ["Core", "UiPlugin", "Gui", "Widgets"]
            designer_requires = ["Core", "Gui", "UiPlugin", "Widgets", "Xml"]
            if self.options.get_safe("opengl", "no") != "no":
                uitools_requires.extend(["OpenGL", "OpenGLWidgets"])
                designer_requires.extend(["OpenGL", "OpenGLWidgets"])
            modules.update({
                "UiPlugin": {"requires": ["Core", "Gui", "Widgets"], "header_only": True},
                "UiTools": {"requires": uitools_requires},
                "Designer": {"requires": designer_requires},
                "Help": {"requires": ["Core", "Gui", "Sql", "Widgets"]},
            })

            # designer plugins only built if qt shared
            if self.options.shared:
                if False: # TODO: add condition based on availability of WebKitWidgets
                    plugins.update({
                        "QWebViewPlugin": {
                            "libs": ["qwebview"],
                            "type": "designer",
                            "requires": ["Core", "Designer", "Gui", "WebKitWidgets", "Widgets"],
                        }
                    })
                if self.options.get_safe("qtactiveqt") and self.settings.os == "Windows":
                    plugins.update({
                        "QAxWidgetPlugin": {
                            "libs": ["qaxwidget"],
                            "type": "designer",
                            "requires": ["AxContainer", "Core", "Designer", "Gui", "Widgets"],
                        }
                    })
                if self.options.qtdeclarative:
                    plugins.update({
                        "QQuickWidgetPlugin": {
                            "libs": ["qquickwidget"],
                            "type": "designer",
                            "requires": ["Core", "Designer", "Gui", "QuickWidgets", "Widgets"],
                        }
                    })
                if False: # TODO: not built for the moment?
                    plugins.update({
                        "QView3DPlugin": {
                            "libs": ["view3d"],
                            "type": "designer",
                            "requires": ["Core", "Designer", "Gui", "OpenGL", "Widgets"],
                        }
                    })
        return {"modules": modules, "plugins": plugins}

    @property
    def _qtwayland_components(self):
        modules = {}
        plugins = {}
        if self.options.gui:
            wayland_compositor_requires = ["Core", "Gui", "wayland::wayland-server"]
            if self.options.get_safe("opengl", "no") != "no":
                wayland_compositor_requires.append("OpenGL")
            if self.options.qtdeclarative:
                wayland_compositor_requires.extend(["Qml", "Quick"])
            modules.update({
                "WaylandClient": {"requires": ["Core", "Gui", "wayland::wayland-client", "wayland::wayland-cursor"]},
                "WaylandCompositor": {"requires": wayland_compositor_requires},
            })
            plugins.update({"QWaylandIntegrationPlugin": {"libs": ["qwayland-generic"], "type": "platforms", "requires": ["Core", "Gui", "WaylandClient"]}})
            # TODO: add tones of plugins
        return {"modules": modules, "plugins": plugins}

    @property
    def _qt3d_components(self):
        modules = {}
        plugins = {}
        if self.options.gui and self.options.get_safe("opengl", "no") != "no":
            modules.update({
                "3DCore": {"requires": ["Core", "Gui", "Network", "Concurrent"]},
                "3DLogic": {"requires": ["Core", "3DCore", "Gui"]},
                "3DInput": {"requires": ["Core", "3DCore", "Gui"]}, # TODO: depends on Gamepad if built, but not yet available
                "3DRender": {"requires": ["Core", "3DCore", "Concurrent", "OpenGL"]},
                "3DExtras": {"requires": ["Core", "Gui", "3DCore", "3DInput", "3DLogic", "3DRender"]},
                "3DAnimation": {"requires": ["Core", "3DCore", "3DRender", "Gui"]},
            })
            plugins.update({
                "DefaultGeometryLoaderPlugin": {"libs": ["defaultgeometryloader"], "type": "geometryloaders", "requires": ["Core", "3DCore", "3DRender", "Gui"]},
                # TODO: This plugin is not created if fbxsdk not installed on the system
                # "fbxGeometryLoaderPlugin": {"libs": ["fbxgeometryloader"], "type": "geometryloaders", "requires": ["Core", "3DCore", "3DRender", "Gui"]},
                "OpenGLRendererPlugin": {"libs": ["openglrenderer"], "type": "renderers", "requires": ["Core", "3DCore", "3DRender", "Gui", "OpenGL"]},
            })
            if self.options.qtdeclarative:
                modules.update({
                    "3DQuick": {"requires": ["Core", "3DCore", "Gui", "Qml", "Quick"]},
                    "3DQuickRender": {"requires": ["Core", "3DCore", "3DQuick", "3DRender", "Gui", "Qml"]},
                    "3DQuickScene2D": {"requires": ["Core", "3DCore", "3DQuick", "3DRender", "Gui", "Qml"]},
                    "3DQuickExtras": {"requires": ["Core", "3DCore", "3DExtras", "3DInput", "3DLogic", "3DQuick", "3DRender", "Gui", "Qml"]},
                    "3DQuickInput": {"requires": ["Core", "3DCore", "3DInput", "3DQuick", "Gui", "Qml"]},
                    "3DQuickAnimation": {"requires": ["Core", "3DAnimation", "3DCore", "3DQuick", "3DRender", "Gui", "Qml"]},
                })
            if self.options.qtshadertools:
                plugins.update({
                    "RhiRendererPlugin": {"libs": ["rhirenderer"], "type": "renderers", "requires": ["Core", "3DCore", "3DRender", "Gui", "ShaderTools"]},
                })
        return {"modules": modules, "plugins": plugins}

    @property
    def _qtimageformats_components(self):
        plugins = {}
        if self.options.gui:
            plugins.update({
                "QTgaPlugin": {"libs": ["qtga"], "type": "imageformats", "requires": ["Core", "Gui"]},
                "QWbmpPlugin": {"libs": ["qwbmp"], "type": "imageformats", "requires": ["Core", "Gui"]},
                "QTiffPlugin": {"libs": ["qtiff"], "type": "imageformats", "requires": ["Core", "Gui"]},
                "QWebpPlugin": {"libs": ["qwebp"], "type": "imageformats", "requires": ["Core", "Gui", "libwebp::libwebp"]},
                "QICNSPlugin": {"libs": ["qicns"], "type": "imageformats", "requires": ["Core", "Gui"]},
                # TODO: eventually add an option for Apple OS: if jasper is not used, QMacJp2Plugin is created instead
                "QJp2Plugin": {"libs": ["qjp2"], "type": "imageformats", "requires": ["Core", "Gui", "jasper::jasper"]},
            })
            if tools.is_apple_os(self.settings.os):
                plugins.update({
                    "QMacHeifPlugin": {
                        "libs": ["qmacheif"],
                        "type": "imageformats",
                        "requires": ["Core", "Gui"],
                        "frameworks": ["CoreFoundation", "CoreGraphics", "ImageIO"],
                    }
                })
        return {"modules": {}, "plugins": plugins}

    @property
    def _qtquickcontrols2_components(self):
        modules = {}
        if self.options.gui and self.options.qtdeclarative:
            modules.update({
                "QuickTemplates2": {"requires": ["Core", "Gui", "Qml", "Quick", "QmlModels"]},
                "QuickControls2": {"requires": ["Core", "Gui", "Qml", "Quick", "QuickTemplates2"]},
                "QuickControls2Impl": {"requires": ["Core", "Gui", "Qml", "Quick", "QuickTemplates2"]},
            })
        return {"modules": modules, "plugins": {}}

    @property
    def _qtcharts_components(self):
        modules = {}
        if self.options.gui and self.options.widgets:
            charts_requires = ["Core", "Gui", "Widgets"]
            if self.options.get_safe("opengl", "no") != "no":
                charts_requires.extend(["OpenGL", "OpenGLWidgets"])
            charts_system_libs = []
            if self.settings.os == "Windows":
                charts_system_libs.append("user32")
            modules.update({"Charts": {"requires": charts_requires, "system_libs": charts_system_libs}})
        return {"modules": modules, "plugins": {}}

    @property
    def _qtdatavis3d_components(self):
        modules = {}
        if self.options.gui and self.options.widgets and self.options.get_safe("opengl", "no") != "no" and self.options.qtdeclarative:
            modules.update({"DataVisualization": {"requires": ["Core", "Gui", "OpenGL", "Qml", "Quick"]}})
        return {"modules": modules, "plugins": {}}

    @property
    def _qtvirtualkeyboard_components(self):
        modules = {}
        plugins = {}
        if self.options.gui and self.options.qtsvg and self.options.qtdeclarative:
            modules.update({"VirtualKeyboard": {"requires": ["Core", "Gui", "Qml", "Quick"]}})
            vkey_plugin_system_libs = ["imm32"] if self.settings.os == "Windows" else []
            plugins.update({
                "QVirtualKeyboardPlugin": {"libs": ["qtvirtualkeyboardplugin"], "type": "platforminputcontexts", "requires": ["Core", "Gui", "Qml", "VirtualKeyboard"], "system_libs": vkey_plugin_system_libs},
                "QtVirtualKeyboardHangulPlugin": {"libs": ["qtvirtualkeyboard_hangul"], "type": "virtualkeyboard", "requires": ["Core", "Gui", "Qml", "VirtualKeyboard"]},
                "QtVirtualKeyboardMyScriptPlugin": {"libs": ["qtvirtualkeyboard_myscript"], "type": "virtualkeyboard", "requires": ["Core", "Gui", "Qml", "VirtualKeyboard"]},
                "QtVirtualKeyboardThaiPlugin": {"libs": ["qtvirtualkeyboard_thai"], "type": "virtualkeyboard", "requires": ["Core", "Gui", "Qml", "VirtualKeyboard"]},
            })
            # TODO: add more plugins?
        return {"modules": modules, "plugins": plugins}

    @property
    def _qtscxml_components(self):
        modules = {}
        plugins = {}
        if self.options.qtdeclarative:
            modules.update({"Scxml": {"requires": ["Core"]}})
            statemachine_requires = ["Core"]
            if self.options.gui:
                statemachine_requires.append("Gui")
            modules.update({"StateMachine": {"requires": statemachine_requires}})
            modules.update({"StateMachineQml": {"requires": ["Core", "Qml", "StateMachine"]}})
            modules.update({"ScxmlQml": {"requires": ["Core", "Qml", "Scxml"]}})
            plugins.update({"QScxmlEcmaScriptDataModelPlugin": {"libs": ["qscxmlecmascriptdatamodel"], "type": "scxmldatamodel", "requires": ["Core", "Scxml", "Qml"]}})
        return {"modules": modules, "plugins": plugins}

    @property
    def _qtnetworkauth_components(self):
        return {
            "modules": {"NetworkAuth": {"requires": ["Core", "Network"]}},
            "plugins": {},
        }

    @property
    def _qtlottie_components(self):
        modules = {}
        if self.options.gui:
            modules.update({"Bodymovin": {"requires": ["Core", "Gui"]}})
        return {"modules": modules, "plugins": {}}

    @property
    def _qtquick3d_components(self):
        modules = {}
        if self.options.gui and self.options.qtdeclarative and self.options.qtshadertools and self.settings.os != "watchOS":
            modules.update({
                "Quick3DUtils": {"requires": ["Core", "Gui"]},
                "Quick3DAssetImport": {"requires": ["Core", "Gui", "Qml", "Quick3DUtils"]},
                "Quick3DRuntimeRender": {"requires": ["Core", "Gui", "Quick", "Quick3DAssetImport", "Quick3DUtils", "ShaderTools"]},
                "Quick3D": {"requires": ["Core", "Gui", "Qml", "Quick", "Quick3DRuntimeRender"]},
                "Quick3DIblBaker": {"requires": ["Core", "Gui", "Quick", "Quick3DRuntimeRender"]},
            })
        return {"modules": modules, "plugins": {}}

    @property
    def _qtshadertools_components(self):
        modules = {}
        if self.options.gui and not self.settings.os == "watchOS":
            modules.update({"ShaderTools": {"requires": ["Core", "Gui"]}})
        return {"modules": modules, "plugins": {}}

    @property
    def _qt5compat_components(self):
        return {
            "modules": {"Core5Compat": {"requires": ["Core"]}},
            "plugins": {},
        }

    @property
    def _qtcoap_components(self):
        return {
            "modules": {"Coap": {"requires": ["Core", "Network"]}},
            "plugins": {},
        }

    @property
    def _qtmqtt_components(self):
        return {
            "modules": {"Mqtt": {"requires": ["Core", "Network"]}},
            "plugins": {},
        }

    @property
    def _qtopcua_components(self):
        modules = {"OpcUa": {"requires": ["Core", "Network"]}}
        plugins = {
            "QOpen62541Plugin": {"libs": ["open62541_backend"], "type": "opcua", "requires": ["Core", "Network", "OpcUa"]},
            # TODO: this one might not be built
            # "QUACppPlugin": {"libs": ["uacpp_backend"], "type": "opcua", "requires": ["Core", "Network", "OpcUa"]},
        }
        return {"modules": modules, "plugins": plugins}
