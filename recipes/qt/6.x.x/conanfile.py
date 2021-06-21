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
                   "qtwayland","qtquickcontrols2", "qtquicktimeline", "qtquick3d", "qtshadertools", "qt5compat",
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
            self.requires("glib/2.68.1")
        if self.options.with_doubleconversion and not self.options.multiconfiguration:
            self.requires("double-conversion/3.1.5")
        if self.options.get_safe("with_freetype", False) and not self.options.multiconfiguration:
            self.requires("freetype/2.10.4")
        if self.options.get_safe("with_fontconfig", False):
            self.requires("fontconfig/2.13.93")
        if self.options.get_safe("with_icu", False):
            self.requires("icu/68.2")
        if self.options.get_safe("with_harfbuzz", False) and not self.options.multiconfiguration:
            self.requires("harfbuzz/2.8.0")
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
                self.requires("xkbcommon/1.2.1")
        if self.settings.os != "Windows" and self.options.get_safe("opengl", "no") != "no":
            self.requires("opengl/system")
        if self.options.with_zstd:
            self.requires("zstd/1.5.0")
        if self.options.get_safe("qtwayland"):
            self.requires("wayland/1.19.0")
        if self.options.with_brotli:
            self.requires("brotli/1.0.9")
        if self.options.qtimageformats:
            self.requires("jasper/2.0.32")
            self.requires("libtiff/4.2.0")
            self.requires("libwebp/1.2.0")
            # TODO: add libmng to create QMngPlugin

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
        if self.options.qtsvg and not self.options.gui:
            raise ConanInvalidConfiguration("qtsvg requires gui")
        if self.options.qtdeclarative and not self.options.qtsvg:
            raise ConanInvalidConfiguration("qtdeclarative requires qtsvg")
        if self.options.qtactiveqt and not (self.options.gui and self.options.widgets):
            raise ConanInvalidConfiguration("qtactiveqt requires gui and widgets")
        if self.options.qttools and not (self.options.qtactiveqt and self.options.qtdeclarative):
            raise ConanInvalidConfiguration("qttools requires qtactiveqt and qtdeclarative")
        if self.options.qtimageformats and not self.options.gui:
            raise ConanInvalidConfiguration("qtimageformats requires gui")
        if self.options.qtquickcontrols2 and not (self.options.gui and self.options.qtdeclarative and self.options.qtsvg and self.options.qtimageformats):
            raise ConanInvalidConfiguration("qtquickcontrols2 requires gui, qtdeclarative, qtsvg and qtimageformats")
        if self.options.qtcharts and not (self.options.gui and self.options.widgets):
            raise ConanInvalidConfiguration("qtcharts requires gui and widgets")

    def package_id(self):
        del self.info.options.cross_compile
        del self.info.options.sysroot
        if self.options.multiconfiguration and self.settings.compiler == "Visual Studio":
            if "MD" in self.settings.compiler.runtime:
                self.info.settings.compiler.runtime = "MD/MDd"
            else:
                self.info.settings.compiler.runtime = "MT/MTd"

    def build_requirements(self):
        self.build_requires("cmake/3.20.2")
        self.build_requires("ninja/1.10.2")
        self.build_requires("pkgconf/1.7.4")
        if self.settings.compiler == "Visual Studio":
            self.build_requires('strawberryperl/5.30.0.1')

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

        def _create_module(module, requires=[]):
            componentname = "qt%s" % module
            assert componentname not in self.cpp_info.components, "Module %s already present in self.cpp_info.components" % module
            self.cpp_info.components[componentname].names["cmake_find_package"] = module
            self.cpp_info.components[componentname].names["cmake_find_package_multi"] = module
            self.cpp_info.components[componentname].libs = ["Qt6%s%s" % (module, libsuffix)]
            self.cpp_info.components[componentname].includedirs = ["include", os.path.join("include", "Qt%s" % module)]
            self.cpp_info.components[componentname].defines = ["QT_%s_LIB" % module.upper()]
            self.cpp_info.components[componentname].requires = _get_corrected_reqs(requires)

        def _create_plugin(pluginname, libname, type, requires):
            componentname = "qt%s" % pluginname
            assert componentname not in self.cpp_info.components, "Plugin %s already present in self.cpp_info.components" % pluginname
            self.cpp_info.components[componentname].names["cmake_find_package"] = pluginname
            self.cpp_info.components[componentname].names["cmake_find_package_multi"] = pluginname
            if not self.options.shared:
                self.cpp_info.components[componentname].libs = [libname + libsuffix]
            self.cpp_info.components[componentname].libdirs = [os.path.join("res", "archdatadir", "plugins", type)]
            self.cpp_info.components[componentname].includedirs = []
            if "Core" not in requires:
                requires.append("Core")
            self.cpp_info.components[componentname].requires = _get_corrected_reqs(requires)

        def _components():
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

            # qtbase
            ## Core
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
            modules.update({
                "Core": {
                    "requires": ["zlib::zlib"] + pcre2() + doubleconversion() + glib() + icu() + zstd(),
                    "system_libs": core_system_libs,
                    "frameworks": core_frameworks,
                }
            })
            ## Concurrent
            modules.update({"Concurrent": {"internal_deps": ["Core"]}})
            ## Sql
            modules.update({"Sql": {"internal_deps": ["Core"]}})
            ## Network
            network_system_libs = []
            network_frameworks = []
            if self.settings.os == "Windows":
                network_system_libs.extend(["advapi32", "dnsapi", "iphlpapi"])
                # which condition?
                # network_system_libs.extend(["Crypt32", "Secur32", "bcrypt", "ncrypt"])
            elif self.settings.os in ["Linux", "FreeBSD"]:
                network_system_libs.extend(["dl"])
            elif tools.is_apple_os(self.settings.os):
                if self.settings.os == "Macos":
                    network_frameworks.extend(["CoreServices", "GSS"])
                if self.settings.os in ["Macos", "iOS"]:
                    network_frameworks.append("SystemConfiguration")
            modules.update({
                "Network": {
                    "internal_deps": ["Core"],
                    "requires": ["zlib::zlib"] + openssl() + brotli() + zstd(),
                    "system_libs": network_system_libs,
                    "frameworks": network_frameworks,
                }
            })
            ## Xml
            modules.update({"Xml": {"internal_deps": ["Core"]}})
            ## DBus
            dbus_system_libs = []
            if self.settings.os == "Windows":
                dbus_system_libs.extend(["advapi32", "netapi32", "user32", "ws2_32"])
            modules.update({"DBus": {"internal_deps": ["Core"], "system_libs": dbus_system_libs}})
            ## Test
            test_frameworks = []
            if tools.is_apple_os(self.settings.os):
                test_frameworks.append("Security")
                if self.settings.os == "Macos":
                    test_frameworks.extend(["AppKit", "ApplicationServices", "Foundation", "IOKit"])
            modules.update({"Test": {"internal_deps": ["Core"], "frameworks": test_frameworks}})

            if self.options.gui:
                ## Gui
                gui_system_libs = []
                gui_frameworks = []
                if self.settings.os == "Windows":
                    gui_system_libs.extend(["advapi32", "gdi32", "ole32", "shell32",
                                            "user32", "d3d11", "dxgi", "dxguid"])
                    # which condition?
                    # gui_system_libs.extend(["d2d1", "dwrite", "uuid"])
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
                        "internal_deps": ["Core", "DBus"],
                        "requires": ["zlib::zlib"] + freetype() + png() + fontconfig() + xorg() +
                                    opengl() + harfbuzz() + jpeg() + vulkan() + glib(),
                        "system_libs": gui_system_libs,
                        "frameworks": gui_frameworks,
                    }
                })
                ## OpenGL
                if self.options.get_safe("opengl", "no") != "no":
                    modules.update({"OpenGL": {"internal_deps": ["Core", "Gui"], "requires": vulkan()}})

                ## platforms plugins
                if self.settings.os == "Android":
                    # TODO: should link to EGL also
                    plugins.update({
                        "QAndroidIntegrationPlugin": {
                            "libs": ["qtforandroid"],
                            "type": "platforms",
                            "internal_deps": ["Core", "Gui"],
                            "system_libs": ["android", "jnigraphics"],
                            "requires": ["sqlite3::sqlite3"],
                        }
                    })
                else:
                    plugins.update({
                        "QMinimalIntegrationPlugin": {
                            "libs": ["qminimal"],
                            "type": "platforms",
                            "internal_deps": ["Core", "Gui"],
                            "requires": freetype(),
                        }
                    })
                    if self.options.get_safe("with_fontconfig"):
                        plugins.update({
                            "QOffscreenIntegrationPlugin": {
                                "libs": ["qoffscreen"],
                                "type": "platforms",
                                "internal_deps": ["Core", "Gui"],
                                "requires": xorg(),
                            }
                        })
                if self.settings.os in ["Linux", "FreeBSD"]:
                    # TODO: depends on Qt::XcbQpaPrivate
                    plugins.update({
                        "QXcbIntegrationPlugin": {
                            "libs": ["qxcb"],
                            "type": "platforms",
                            "internal_deps": ["Core", "Gui"],
                        }
                    })
                    # TODO: more plugins for xcb
                if self.settings.os in ["iOS", "tvOS"]:
                    iosintegrationplugin_frameworks = ["AudioToolbox", "Foundation", "Metal", "QuartzCore", "UIKit"]
                    if self.settings.os != "tvOS":
                        iosintegrationplugin_frameworks.append("AssetsLibrary")
                    plugins.update({
                        "QIOSIntegrationPlugin": {
                            "libs": ["qios"],
                            "type": "platforms",
                            "internal_deps": ["Core", "Gui"],
                            "requires": opengl(),
                            "frameworks": iosintegrationplugin_frameworks,
                        }
                    })
                if self.settings.os == "Macos":
                    plugins.update({
                        "QCocoaIntegrationPlugin": {
                            "libs": ["qcocoa"],
                            "type": "platforms",
                            "internal_deps": ["Core", "Gui"],
                            "frameworks": ["AppKit", "Carbon", "CoreServices", "CoreVideo",
                                           "IOKit", "IOSurface", "Metal", "QuartzCore"],
                        }
                    })
                if self.settings.os == "Windows":
                    windowsintegrationplugin_internal_deps = ["Core", "Gui"]
                    windowsintegrationplugin_system_libs = ["advapi32", "dwmapi", "gdi32", "imm32", "ole32",
                                                            "oleaut32", "shell32", "shlwapi", "user32", "winmm",
                                                            "winspool", "wtsapi32"]
                    if self.options.get_safe("opengl", "no") != "no":
                        windowsintegrationplugin_internal_deps.append("OpenGL")
                        if self.options.get_safe("opengl", "no") != "dynamic":
                            windowsintegrationplugin_system_libs.append("opengl32")
                    if self.settings.compiler == "gcc":
                        windowsintegrationplugin_system_libs.append("uuid")
                    plugins.update({
                        "QWindowsIntegrationPlugin": {
                            "libs": ["qwindows"],
                            "type": "platforms",
                            "internal_deps": windowsintegrationplugin_internal_deps,
                            "system_libs": windowsintegrationplugin_system_libs,
                        }
                    })

                ## imageformats plugins
                plugins.update({
                    "QICOPlugin": {
                        "libs": ["qico"],
                        "type": "imageformats",
                        "internal_deps": ["Core", "Gui"],
                    }
                })
                plugins.update({
                    "QJpegPlugin": {
                        "libs": ["qjpeg"],
                        "type": "imageformats",
                        "internal_deps": ["Core", "Gui"],
                        "requires": jpeg(),
                    }
                })
                plugins.update({
                    "QGifPlugin": {
                        "libs": ["qgif"],
                        "type": "imageformats",
                        "internal_deps": ["Core", "Gui"],
                    }
                })

                # TODO: generic plugins

                if self.options.widgets:
                    ## Widgets
                    widgets_system_libs = []
                    widgets_frameworks = []
                    if self.settings.os == "Windows":
                        widgets_system_libs.extend(["dwmapi", "shell32", "uxtheme"])
                    elif self.settings.os == "Macos":
                        widgets_frameworks.extend(["AppKit"])
                    modules.update({
                        "Widgets": {
                            "internal_deps": ["Core", "Gui"],
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
                                "internal_deps": ["Core", "Gui", "Widgets"],
                            }
                        })
                    if self.settings.os == "Macos":
                        plugins.update({
                            "QMacStylePlugin": {
                                "libs": ["qmacstyle"],
                                "type": "styles",
                                "internal_deps": ["Core", "Gui", "Widgets"],
                                "frameworks": ["AppKit"]
                            }
                        })
                    if self.settings.os == "Windows":
                        plugins.update({
                            "QWindowsVistaStylePlugin": {
                                "libs": ["qwindowsvistastyle"],
                                "type": "styles",
                                "internal_deps": ["Core", "Gui", "Widgets"],
                                "system_libs": ["gdi32", "user32", "uxtheme"]
                            }
                        })

                    ## PrintSupport
                    printsupport_system_libs = []
                    printsupport_frameworks = []
                    if self.settings.os == "Windows":
                        printsupport_system_libs.extend(["gdi32", "user32", "comdlg32", "winspool"])
                    elif self.settings.os == "Macos":
                        printsupport_frameworks.extend(["ApplicationServices", "AppKit"])
                        printsupport_system_libs.extend(["cups"])
                    modules.update({
                        "PrintSupport": {
                            "internal_deps": ["Core", "Gui", "Widgets"],
                            "system_libs": printsupport_system_libs,
                            "frameworks": printsupport_system_libs,
                        }
                    })

                    # TODO: printsupport plugins

                    ## OpenGLWidgets
                    if self.options.get_safe("opengl", "no") != "no":
                        modules.update({"OpenGLWidgets": {"internal_deps": ["OpenGL", "Widgets"]}})

            # TODO: add missing modules: DeviceDiscoverySupport, FbSupport

            ## sql plugins
            if self.options.with_sqlite3:
                plugins.update({
                    "QSQLiteDriverPlugin": {
                        "libs": ["qsqlite"],
                        "type": "sqldrivers",
                        "internal_deps": ["Core", "Sql"],
                        "requires": ["sqlite3::sqlite3"],
                    }
                })
            if self.options.with_pq:
                plugins.update({
                    "QPSQLDriverPlugin": {
                        "libs": ["qsqlpsql"],
                        "type": "sqldrivers",
                        "internal_deps": ["Core", "Sql"],
                        "requires": ["libpq::libpq"],
                    }
                })
            if self.options.with_odbc:
                # TODO: handle windows (odbc is a system lib on Windows)
                if self.settings.os != "Windows":
                    plugins.update({
                        "QODBCDriverPlugin": {
                            "libs": ["qsqlodbc"],
                            "type": "sqldrivers",
                            "internal_deps": ["Core", "Sql"],
                            "requires": ["odbc::odbc"],
                        }
                    })

            # qtsvg
            if self.options.qtsvg:
                if self.options.gui:
                    modules.update({"Svg": {"internal_deps": ["Gui"]}})
                    plugins.update({
                        "QSvgIconPlugin": {"libs": ["qsvgicon"], "type": "iconengines", "internal_deps": ["Core", "Gui", "Svg"]},
                        "QSvgPlugin": {"libs": ["qsvg"], "type": "imageformats", "internal_deps": ["Core", "Gui", "Svg"]},
                    })
                    if self.options.widgets:
                        modules.update({"SvgWidgets": {"internal_deps": ["Core", "Gui", "Svg", "Widgets"]}})

            # qtdeclarative
            if self.options.qtdeclarative:
                qml_system_libs = []
                if self.settings.os == "Windows":
                    qml_system_libs = ["shell32"]
                elif self.settings.os in ["Linux", "FreeBSD"] and not self.options.shared:
                    qml_system_libs = ["rt"]
                modules.update({
                    "Qml": {"internal_deps": ["Core", "Network"], "system_libs": qml_system_libs},
                    "QmlModels": {"internal_deps": ["Core", "Qml"]},
                    "QmlWorkerScript": {"internal_deps": ["Core", "Qml"]},
                    "QmlLocalStorage": {"internal_deps": ["Core", "Qml", "Sql"]},
                    "LabsSettings": {"internal_deps": ["Core", "Qml"]},
                    "LabsQmlModels": {"internal_deps": ["Core", "Qml"]},
                    "LabsFolderListModel": {"internal_deps": ["Qml", "QmlModels"]},
                    "PacketProtocol": {"internal_deps": ["Core"]},
                    "QmlDevTools": {"internal_deps": ["Core"]},
                    "QmlDom": {"internal_deps": ["Core", "QmlDevTools"]},
                    "QmlCompiler": {"internal_deps": ["Core", "QmlDevTools"]},
                    "QmlDebug": {"internal_deps": ["Core", "Network", "PacketProtocol", "Qml"]},
                })
                plugins.update({
                    "QQmlNativeDebugConnectorFactory": {"libs": ["qmldbg_native"], "type": "qmltooling", "internal_deps": ["Core", "PacketProtocol", "Qml"]},
                    "QDebugMessageServiceFactory": {"libs": ["qmldbg_messages"], "type": "qmltooling", "internal_deps": ["Core", "PacketProtocol", "Qml"]},
                    "QQmlProfilerServiceFactory": {"libs": ["qmldbg_profiler"], "type": "qmltooling", "internal_deps": ["Core", "PacketProtocol", "Qml"]},
                    "QQmlDebuggerServiceFactory": {"libs": ["qmldbg_debugger"], "type": "qmltooling", "internal_deps": ["Core", "PacketProtocol", "Qml"]},
                    "QQmlNativeDebugServiceFactory": {"libs": ["qmldbg_nativedebugger"], "type": "qmltooling", "internal_deps": ["Core", "PacketProtocol", "Qml"]},
                    "QQmlDebugServerFactory": {"libs": ["qmldbg_server"], "type": "qmltooling", "internal_deps": ["PacketProtocol", "Qml"]},
                    "QTcpServerConnectionFactory": {"libs": ["qmldbg_tcp"], "type": "qmltooling", "internal_deps": ["Network", "Qml"]},
                    "QLocalClientConnectionFactory": {"libs": ["qmldbg_local"], "type": "qmltooling", "internal_deps": ["Qml"]},
                })
                if self.options.gui:
                    quick_internal_deps = ["Core", "Gui", "Qml", "QmlModels", "Network"]
                    if self.options.get_safe("opengl", "no") != "no":
                        quick_internal_deps.append("OpenGL")
                    quick_system_libs = []
                    if self.settings.os == "Windows":
                        quick_system_libs = ["user32"]
                    modules.update({
                        "Quick": {"internal_deps": quick_internal_deps, "system_libs": quick_system_libs},
                        "QuickShapes": {"internal_deps": ["Core", "Gui", "Qml", "Quick"]},
                        "QuickLayouts": {"internal_deps": ["Core", "Gui", "Qml", "Quick"]},
                        "QuickTest": {"internal_deps": ["Core", "Gui", "Qml", "Quick", "Test"]},
                        "QuickParticles": {"internal_deps": ["Core", "Gui", "Qml", "Quick"]},
                        "LabsAnimation": {"internal_deps": ["Qml", "Quick"]},
                        "LabsWavefrontMesh": {"internal_deps": ["Core", "Gui", "Quick"]},
                        "LabsSharedImage": {"internal_deps": ["Core", "Gui", "Quick"]},
                    })
                    plugins.update({
                        "QQmlInspectorServiceFactory": {"libs": ["qmldbg_inspector"], "type": "qmltooling", "internal_deps": ["Core", "Gui", "PacketProtocol", "Qml", "Quick"]},
                        "QQuickProfilerAdapterFactory": {"libs": ["qmldbg_quickprofiler"], "type": "qmltooling", "internal_deps": ["Core", "Gui", "PacketProtocol", "Qml", "Quick"]},
                        "QQmlPreviewServiceFactory": {"libs": ["qmldbg_preview"], "type": "qmltooling", "internal_deps": ["Core", "Gui", "Network", "PacketProtocol", "Qml", "Quick"]},
                    })
                    if self.options.widgets:
                        quickwidgets_internal_deps = ["Core", "Gui", "Qml", "Quick", "Widgets"]
                        if self.options.get_safe("opengl", "no") != "no":
                            quickwidgets_internal_deps.append("OpenGL")
                        modules.update({"QuickWidgets": {"internal_deps": quickwidgets_internal_deps}})

            # qtactiveqt (WIP)
            if self.options.qtactiveqt and self.settings.os == "Windows":
                if self.options.gui and self.options.widgets:
                    modules.update({
                        "AxBase": {"internal_deps": ["Gui", "Widgets"]},
                        "AxServer": {"internal_deps": ["AxBase"]},
                        "AxContainer": {"internal_deps": ["AxBase"]},
                    })

            # qttools (WIP)
            if self.options.qttools:
                if self.options.gui and self.options.widgets:
                    modules.update({
                        "UiPlugin": {"internal_deps": ["Gui", "Widgets"]},
                        "UiTools": {"internal_deps": ["UiPlugin", "Gui", "Widgets"]},
                        "Designer": {"internal_deps": ["Gui", "UiPlugin", "Widgets", "Xml"]},
                        "Help": {"internal_deps": ["Gui", "Sql", "Widgets"]},
                    })

            # TODO: qttranslations?

            # TODO: qtdoc?

            # qtwayland (WIP)
            if self.options.get_safe("qtwayland"):
                if self.options.gui:
                    modules.update({
                        "WaylandClient": {"internal_deps": ["Gui"], "requires": ["wayland::wayland-client"]},
                        "WaylandCompositor": {"internal_deps": ["Gui"], "requires": ["wayland::wayland-client"]},
                    })

            # qt3d (WIP)
            if self.options.qt3d:
                if self.options.gui:
                    modules.update({
                        "3DCore": {"internal_deps": ["Gui", "Network"]},
                        "3DInput": {"internal_deps": ["3DCore", "Gui"]},
                        "3DLogic": {"internal_deps": ["3DCore", "Gui"]},
                    })
                    if self.options.get_safe("opengl", "no") != "no":
                        modules.update({
                            "3DRender": {"internal_deps": ["3DCore", "OpenGL"]},
                            "3DAnimation": {"internal_deps": ["3DCore", "3DRender", "Gui"]},
                            "3DExtras": {"internal_deps": ["Gui", "3DCore", "3DInput", "3DLogic", "3DRender"]},
                        })
                    if self.options.qtdeclarative:
                        modules.update({
                            "3DQuick": {"internal_deps": ["3DCore", "Gui", "Qml", "Quick"]},
                            "3DQuickInput": {"internal_deps": ["3DCore", "3DInput", "3DQuick", "Gui", "Qml"]},
                        })
                    if self.options.get_safe("opengl", "no") != "no" and self.options.qtdeclarative:
                        modules.update({
                            "3DQuickAnimation": {"internal_deps": ["3DAnimation", "3DCore", "3DQuick", "3DRender", "Gui", "Qml"]},
                            "3DQuickExtras": {"internal_deps": ["3DCore", "3DExtras", "3DInput", "3DQuick", "3DRender", "Gui", "Qml"]},
                            "3DQuickRender": {"internal_deps": ["3DCore", "3DQuick", "3DRender", "Gui", "Qml"]},
                            "3DQuickScene2D": {"internal_deps": ["3DCore", "3DQuick", "3DRender", "Gui", "Qml"]},
                        })

                _create_plugin("DefaultGeometryLoaderPlugin", "defaultgeometryloader", "geometryloaders", ["3DCore", "3DRender", "Gui"])
                _create_plugin("fbxGeometryLoaderPlugin", "fbxgeometryloader", "geometryloaders", ["3DCore", "3DRender", "Gui"])

            # qtimageformats
            if self.options.qtimageformats:
                if self.options.gui:
                    plugins.update({
                        "QTgaPlugin": {"libs": ["qtga"], "type": "imageformats", "internal_deps": ["Core", "Gui"]},
                        "QWbmpPlugin": {"libs": ["qwbmp"], "type": "imageformats", "internal_deps": ["Core", "Gui"]},
                        "QTiffPlugin": {"libs": ["qtiff"], "type": "imageformats", "internal_deps": ["Core", "Gui"], "requires": ["libtiff::libtiff"]},
                        "QWebpPlugin": {"libs": ["qwebp"], "type": "imageformats", "internal_deps": ["Core", "Gui"], "requires": ["libwebp::libwebp"]},
                        "QICNSPlugin": {"libs": ["qicns"], "type": "imageformats", "internal_deps": ["Core", "Gui"]},
                        # TODO: eventually add an option for Apple OS: if jasper is not used, QMacJp2Plugin is created instead
                        "QJp2Plugin": {"libs": ["qjp2"], "type": "imageformats", "internal_deps": ["Core", "Gui"], "requires": ["jasper::jasper"]},
                    })
                    if tools.is_apple_os(self.settings.os):
                        plugins.update({
                            "QMacHeifPlugin": {
                                "libs": ["qmacheif"],
                                "type": "imageformats",
                                "internal_deps": ["Core", "Gui"],
                                "frameworks": ["CoreFoundation", "CoreGraphics", "ImageIO"],
                            }
                        })

            # qtquickcontrols2
            if self.options.qtquickcontrols2:
                if self.options.gui and self.options.qtdeclarative:
                    modules.update({
                        "QuickTemplates2": {"internal_deps": ["Core", "Gui", "Qml", "Quick", "QmlModels"]},
                        "QuickControls2": {"internal_deps": ["Core", "Gui", "Qml", "Quick", "QuickTemplates2"]},
                        "QuickControls2Impl": {"internal_deps": ["Core", "Gui", "Qml", "Quick", "QuickTemplates2"]},
                    })

            # qtcharts
            if self.options.qtcharts:
                if self.options.gui and self.options.widgets:
                    charts_internal_deps = ["Core", "Gui", "Widgets"]
                    if self.options.get_safe("opengl", "no") != "no":
                        charts_internal_deps.extend(["OpenGL", "OpenGLWidgets"])
                    charts_system_libs = []
                    if self.settings.os == "Windows":
                        charts_system_libs.append("user32")
                    modules.update({"Charts": {"internal_deps": charts_internal_deps, "system_libs": charts_system_libs}})

            # qtdatavis3d (WIP)
            if self.options.qtdatavis3d:
                if self.options.gui and self.options.get_safe("opengl", "no") != "no" and self.options.qtdeclarative:
                    modules.update({"DataVisualization": {"internal_deps": ["Gui", "OpenGL", "Qml", "Quick"]}})

            # qtvirtualkeyboard (WIP)
            if self.options.qtvirtualkeyboard:
                if self.options.gui and self.options.qtdeclarative:
                    modules.update({"VirtualKeyboard": {"internal_deps": ["Gui", "Qml", "Quick"]}})

                _create_plugin("QVirtualKeyboardPlugin", "qtvirtualkeyboardplugin", "platforminputcontexts", ["Gui", "Qml", "VirtualKeyboard"])
                _create_plugin("QtVirtualKeyboardHangulPlugin", "qtvirtualkeyboard_hangul", "virtualkeyboard", ["Gui", "Qml", "VirtualKeyboard"])
                _create_plugin("QtVirtualKeyboardMyScriptPlugin", "qtvirtualkeyboard_myscript", "virtualkeyboard", ["Gui", "Qml", "VirtualKeyboard"])
                _create_plugin("QtVirtualKeyboardThaiPlugin", "qtvirtualkeyboard_thai", "virtualkeyboard", ["Gui", "Qml", "VirtualKeyboard"])

            # qtscxml (WIP)
            if self.options.qtscxml:
                modules.update({"StateMachine": {}})
                modules.update({"Scxml": {}})
                if self.options.qtdeclarative:
                    modules.update({"StateMachineQml": {"internal_deps": ["StateMachine", "Qml"]}})
                    modules.update({"ScxmlQml": {"internal_deps": ["Scxml", "Qml"]}})

                _create_plugin("QScxmlEcmaScriptDataModelPlugin", "qscxmlecmascriptdatamodel", "scxmldatamodel", ["Scxml", "Qml"])

            # qtnetworkauth (WIP)
            if self.options.qtnetworkauth:
                modules.update({"NetworkAuth": {"internal_deps": ["Network"]}})

            # qtlottie (WIP)
            if self.options.qtlottie:
                if self.options.gui:
                    modules.update({"Bodymovin": {"internal_deps": ["Gui"]}})

            # TODO: qtquicktimeline?

            # qtquick3d (WIP)
            if self.options.qtquick3d:
                if self.options.gui:
                    modules.update({"Quick3DUtils": {"internal_deps": ["Gui"]}})
                    if self.options.qtdeclarative:
                        modules.update({"Quick3DAssetImport": {"internal_deps": ["Gui", "Qml", "Quick3DUtils"]}})
                        if self.options.qtshadertools:
                            modules.update({
                                "Quick3DRuntimeRender": {"internal_deps": ["Gui", "Quick", "Quick3DAssetImport", "Quick3DUtils", "ShaderTools"]},
                                "Quick3D": {"internal_deps": ["Gui", "Qml", "Quick", "Quick3DRuntimeRender"]},
                            })

            # qtshadertools (WIP)
            if self.options.qtshadertools:
                if self.options.gui:
                    modules.update({"ShaderTools": {"internal_deps": ["Gui"]}})

            # qt5compat (WIP)
            if self.options.qt5compat:
                modules.update({"Core5Compat": {}})

            # qtcoap (WIP)
            if self.options.get_safe("qtcoap"):
                modules.update({"Coap": {"internal_deps": ["Network"]}})

            # qtmqtt (WIP)
            if self.options.get_safe("qtmqtt"):
                modules.update({"Mqtt": {"internal_deps": ["Network"]}})

            # qtopcua (WIP)
            if self.options.get_safe("qtopcua"):
                modules.update({"OpcUa": {"internal_deps": ["Network"]}})

                _create_plugin("QOpen62541Plugin", "open62541_backend", "opcua", ["Network", "OpcUa"])
                _create_plugin("QUACppPlugin", "uacpp_backend", "opcua", ["Network", "OpcUa"])

            return {
                "modules": modules,
                "plugins": plugins,
            }


        if tools.Version(self.version) < "6.1.0":
            self.cpp_info.components["qtCore"].libs.append("Qt6Core_qobject%s" % libsuffix)

        if self.options.qtdeclarative:
            self.cpp_info.components["qtQml"].build_modules["cmake_find_package"].append(self._cmake_qt6_private_file("Qml"))
            self.cpp_info.components["qtQml"].build_modules["cmake_find_package_multi"].append(self._cmake_qt6_private_file("Qml"))
            self.cpp_info.components["qtQmlImportScanner"].names["cmake_find_package"] = "QmlImportScanner" # this is an alias for Qml and there to integrate with existing consumers
            self.cpp_info.components["qtQmlImportScanner"].names["cmake_find_package_multi"] = "QmlImportScanner"
            self.cpp_info.components["qtQmlImportScanner"].requires = _get_corrected_reqs(["Qml"])

        if self.options.qttools and self.options.gui and self.options.widgets:
            self.cpp_info.components["qtUiPlugin"].libs = [] # this is a collection of abstract classes, so this is header-only
            self.cpp_info.components["qtUiPlugin"].libdirs = []

        if self.options.qtactiveqt and self.options.gui and self.options.widgets:
            self.cpp_info.components["qtAxServer"].system_libs.append("shell32")
            self.cpp_info.components["qtAxServer"].defines.append("QAXSERVER")

        if self.settings.os != "Windows":
            self.cpp_info.components["qtCore"].cxxflags.append("-fPIC")

        self.cpp_info.components["qtCore"].builddirs.append(os.path.join("res","archdatadir","bin"))
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
