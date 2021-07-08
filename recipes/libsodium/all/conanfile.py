from conans import ConanFile, AutoToolsBuildEnvironment, tools, MSBuild
from conans.errors import ConanInvalidConfiguration
import os

required_conan_version = ">=1.33.0"


class LibsodiumConan(ConanFile):
    name        = "libsodium"
    description = "A modern and easy-to-use crypto library."
    license     = "ISC"
    url         = "https://github.com/conan-io/conan-center-index"
    homepage    = "https://download.libsodium.org/doc/"
    exports_sources = ["patches/**"]
    settings    = "os", "compiler", "arch", "build_type"
    topics = ("sodium", "libsodium", "encryption", "signature", "hashing")

    short_paths = True

    options = {
        "shared": [True, False],
        "fPIC": [True, False],
        "use_soname": [True, False],
        "PIE": [True, False],
    }

    default_options = {
        "shared": False,
        "fPIC": True,
        "use_soname": True,
        "PIE": False,
    }

    _autotools = None

    @property
    def _source_subfolder(self):
        return "source_subfolder"

    @property
    def _android_id_str(self):
        return "androideabi" if str(self.settings.arch) in ["armv6", "armv7"] else "android"

    @property
    def _is_mingw(self):
        return self.settings.os == "Windows" and self.settings.compiler == "gcc"

    @property
    def _vs_configuration(self):
        configuration = ""
        if self.options.shared:
            configuration += "Dyn"
        else:
            configuration += "Static"
        build_type = "Debug" if self.settings.build_type == "Debug" else "Release"
        configuration += build_type
        return configuration

    @property
    def _vs_sln_folder(self):
        return {
            "14": "vs2015",
            "15": "vs2017",
            "16": "vs2019"
        }.get(str(self.settings.compiler.version), False)

    def config_options(self):
        if self.settings.os == "Windows":
            del self.options.fPIC

    def configure(self):
        if self.options.shared:
            del self.options.fPIC
        del self.settings.compiler.libcxx
        del self.settings.compiler.cppstd

    def validate(self):
        if self.settings.compiler == "Visual Studio":
            if self.options.shared and "MT" in str(self.settings.compiler.runtime):
                raise ConanInvalidConfiguration("Cannot build shared libsodium libraries with MT(d) runtime")
            if not self._vs_sln_folder:
                raise ConanInvalidConfiguration("Unsupported Visual Studio version: {}".format(self.settings.compiler.version))

    def build_requirements(self):
        if tools.os_info.is_windows and self.settings.compiler != "Visual Studio" and \
           not tools.get_env("CONAN_BASH_PATH"):
            self.build_requires("msys2/cci.latest")
        if self._is_mingw:
            self.build_requires("libtool/2.4.6")

    def source(self):
        tools.get(**self.conan_data["sources"][self.version],
                  destination=self._source_subfolder, strip_root=True)

    def _build_visual(self):
        sln_path = os.path.join(self.build_folder, self._source_subfolder, "builds", "msvc", self._vs_sln_folder, "libsodium.sln")

        msbuild = MSBuild(self)
        msbuild.build(sln_path, upgrade_project=False, platforms={"x86": "Win32"}, build_type=self._vs_configuration)

    def _build_emscripten(self):
        self.run("./dist-build/emscripten.sh --standard", cwd=self._source_subfolder, win_bash=tools.os_info.is_windows)

    def _configure_autotools(self):
        if self._autotools:
            return self._autotools

        yes_no = lambda v: "yes" if v else "no"
        args = [
            "--enable-shared={}".format(yes_no(self.options.shared)),
            "--enable-static={}".format(yes_no(not self.options.shared)),
            "--enable-soname-versions={}".format(yes_no(self.options.use_soname)),
            "--enable-pie={}".format(yes_no(not self.options.PIE)),
        ]
        if self.options.get_safe("fPIC"):
            args.append("--with-pic")

        if self.settings.os == "Android":
            host_arch = "{}-linux-{}".format(tools.to_android_abi(self.settings.arch), self._android_id_str)
        elif tools.is_apple_os(self.settings.os):
            host_arch = "{}-apple-{}".format(self.settings.arch, "ios" if self.settings.os == "iOS" else "darwin")
        elif self._is_mingw:
            host_arch = "{}-w64-mingw32".format("i686" if self.settings.arch == "x86" else self.settings.arch)
        elif self.settings.os == "Neutrino":
            neutrino_archs = {
                "x86_64": "x86_64-pc",
                "x86": "i586-pc",
                "armv7": "arm-unknown",
                "armv8": "aarch64-unknown",
            }
            if self.settings.os.version == "7.0" and str(self.settings.arch) in neutrino_archs:
                host_arch = "{}-nto-qnx7.0.0".format(neutrino_archs[str(self.settings.arch)])
                if self.settings.arch == "armv7":
                    host_arch += "eabi"

        host = None
        if host_arch:
            host = False
            args.append("--host=%s" % host_arch)

        self._autotools = AutoToolsBuildEnvironment(self, win_bash=tools.os_info.is_windows)
        self._autotools.configure(args=args, configure_dir=self._source_subfolder, host=host)
        return self._autotools

    def _build_autotools(self):
        if self._is_mingw:
            with tools.chdir(self._source_subfolder):
                self.run("{} -fiv".format(tools.get_env("AUTORECONF")), win_bash=tools.os_info.is_windows)
        autotools = self._configure_autotools()
        autotools.make()

    def build(self):
        for patch in self.conan_data.get("patches", {}).get(self.version, []):
            tools.patch(**patch)
        if self.settings.os == "Macos":
            tools.replace_in_file(os.path.join(self._source_subfolder, "configure"), r"-install_name \$rpath/", "-install_name ")
        if self.settings.compiler == "Visual Studio":
            self._build_visual()
        elif self.settings.os == "Emscripten":
            self._build_emscripten()
        else:
            self._build_autotools()

    def _package_visual(self):
        self.copy("*.lib", dst="lib", keep_path=False)
        self.copy("*.dll", dst="bin", keep_path=False)
        inc_src = os.path.join(self._source_subfolder, "src", self.name, "include")
        self.copy("*.h", src=inc_src, dst="include", keep_path=True, excludes=("*/private/*"))

    def _package_emscripten(self):
        prefix = os.path.join(self._source_subfolder, "libsodium-js")
        lib_folder = os.path.join(prefix, "lib")
        self.copy("*.h", dst="include", src=os.path.join(prefix, "include"))
        self.copy("*.a", dst="lib", src=lib_folder)
        self.copy("*.so*", dst="lib", src=lib_folder, symlinks=True)
        self.copy("*.dylib", dst="lib", src=lib_folder, symlinks=True)

    def _package_autotools(self):
        autotools = self._configure_autotools()
        autotools.install()
        tools.rmdir(os.path.join(self.package_folder, "lib", "pkgconfig"))
        tools.remove_files_by_mask(os.path.join(self.package_folder, "lib"), "*.la")

    def package(self):
        self.copy("*LICENSE", dst="licenses", keep_path=False)
        if self.settings.compiler == "Visual Studio":
            self._package_visual()
        elif self.settings.os == "Emscripten":
            self._package_emscripten()
        else:
            self._package_autotools()

    def package_info(self):
        self.cpp_info.names["pkg_config"] = "libsodium"
        self.cpp_info.libs = ["{}sodium".format("lib" if self.settings.compiler == "Visual Studio" else "")]
        if not self.options.shared:
            self.cpp_info.defines = ["SODIUM_STATIC"]
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.cpp_info.system_libs = ["pthread"]
