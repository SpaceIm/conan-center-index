from conans import ConanFile, tools, AutoToolsBuildEnvironment
from conans.errors import ConanInvalidConfiguration
import os
import shutil

required_conan_version = ">=1.33.0"


class LibEstConan(ConanFile):
    name = "libest"
    license = "BSD-3-Clause"
    description = "EST is used for secure certificate enrollment"
    topics = ("conan", "EST", "RFC 7030", "certificate enrollment")
    homepage = "https://github.com/cisco/libest"
    url = "https://github.com/conan-io/conan-center-index"
    settings = "os", "compiler", "build_type", "arch"
    exports_sources = "patches/**"
    options = {"shared": [True, False], "fPIC": [True, False]}
    default_options = {"shared": False, "fPIC": True}

    _autotools = None

    @property
    def _source_subfolder(self):
        return "source_subfolder"

    @property
    def _build_subfolder(self):
        return "build_subfolder"

    def config_options(self):
        if self.settings.os == "Windows":
            del self.options.fPIC

    def configure(self):
        if self.options.shared:
            del self.options.fPIC
        del self.settings.compiler.libcxx
        del self.settings.compiler.cppstd

    def requirements(self):
        self.requires("openssl/1.1.1k")

    def validate(self):
        if self.settings.os == "Windows":
            raise ConanInvalidConfiguration("Platform is currently not supported by this recipe")

    def build_requirements(self):
        self.build_requires("gnu-config/cci.20201022")

    def source(self):
        tools.get(**self.conan_data["sources"][self.version],
                  destination=self._source_subfolder, strip_root=True)

    def _configure_autotools(self):
        if not self._autotools:
            self._autotools = AutoToolsBuildEnvironment(self)
            # TODO:
            # - Static only build: https://github.com/cisco/libest/blob/70824ddc09bee661329b9416082d88566efefb32/intro.txt#L140
            # - Release build: https://github.com/cisco/libest/blob/70824ddc09bee661329b9416082d88566efefb32/intro.txt#L253
            args = ["--with-ssl-dir={}".format(self.deps_cpp_info["openssl"].rootpath)]
            if self.options.shared:
                 args.extend(["--enable-shared", "--disable-static"])
            else:
                 args.extend(["--disable-shared", "--enable-static"])
            self._autotools.configure(args=args)
        return self._autotools

    @property
    def _user_info_build(self):
        return getattr(self, "user_info_build", None) or self.deps_user_info

    def build(self):
        for patch in self.conan_data.get("patches", {}).get(self.version, []):
            tools.patch(**patch)
        shutil.copy(self._user_info_build["gnu-config"].CONFIG_SUB,
                    os.path.join(self._source_subfolder, "config", "config.sub"))
        shutil.copy(self._user_info_build["gnu-config"].CONFIG_GUESS,
                    os.path.join(self._source_subfolder, "config", "config.guess"))
        with tools.chdir(self._source_subfolder):
            autotools = self._configure_autotools()
            autotools.make()

    def package(self):
        self.copy("*LICENSE", src=self._source_subfolder, dst="licenses")
        with tools.chdir(self._source_subfolder):
            autotools = self._configure_autotools()
            autotools.install()
        os.unlink(os.path.join(self.package_folder, "lib", "libest.la"))

    def package_info(self):
        self.cpp_info.libs = ["est"]
        if self.settings.os == "Linux":
            self.cpp_info.system_libs = ["dl", "pthread"]
