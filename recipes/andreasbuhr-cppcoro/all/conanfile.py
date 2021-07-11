import os
from conans import ConanFile, tools, CMake
from conans.errors import ConanInvalidConfiguration

required_conan_version = ">=1.33.0"

class AndreasbuhrCppCoroConan(ConanFile):
    name = "andreasbuhr-cppcoro"
    description = "A library of C++ coroutine abstractions for the coroutines TS"
    topics = ("conan", "cpp", "async", "coroutines")
    url = "https://github.com/conan-io/conan-center-index"
    homepage = "https://github.com/andreasbuhr/cppcoro"
    license = "MIT"
    settings = "os", "compiler", "build_type", "arch"
    provides = "cppcoro"

    exports_sources = ["CMakeLists.txt", "patches/**"]
    generators = "cmake"

    options = {
        "shared": [True, False],
        "fPIC": [True, False],
    }
    default_options = {
        "shared": False,
        "fPIC": True,
    }

    _cmake = None

    @property
    def _source_subfolder(self):
        return "source_subfolder"

    @property
    def _minimum_compilers_version(self):
        return {
            "Visual Studio": "15",
            "gcc": "10",
            "clang": "8",
            "apple-clang": "10",
        }

    def config_options(self):
        if self.settings.os == "Windows":
            del self.options.fPIC

    def validate(self):
        # We can't simply check for C++20, because clang and MSVC support the coroutine TS despite not having labeled (__cplusplus macro) C++20 support
        min_version = self._minimum_compilers_version.get(str(self.settings.compiler))
        if not min_version:
            self.output.warn("{} recipe lacks information about the {} compiler support.".format(
                self.name, self.settings.compiler))
        else:
            if tools.Version(self.settings.compiler.version) < min_version:
                raise ConanInvalidConfiguration("{} requires coroutine TS support. The current compiler {} {} does not support it.".format(
                    self.name, self.settings.compiler, self.settings.compiler.version))

        # Currently clang expects coroutine to be implemented in a certain way (under std::experiemental::), while libstdc++ puts them under std::
        # There are also other inconsistencies, see https://bugs.llvm.org/show_bug.cgi?id=48172
        # This should be removed after both gcc and clang implements the final coroutine TS
        if self.settings.compiler == "clang" and self.settings.compiler.get_safe("libcxx") == "libstdc++":
            raise ConanInvalidConfiguration("{} does not support clang with libstdc++. Use libc++ instead.".format(self.name))

        # TODO remove once figured out why clang 11/libc++ doesn't build on CCI
        # (due to unable to find std::experiemental::noop_coroutine, author is unable to reproduce on local machine)
        if self.settings.compiler == "clang" and self.settings.compiler.version == "11":
            raise ConanInvalidConfiguration("WIP: {} currently doesn't build on clang 11".format(self.name))

    def configure(self):
        if self.options.shared:
            del self.options.fPIC

    def source(self):
       tools.get(**self.conan_data["sources"][self.version], destination=self._source_subfolder, strip_root=True)

    def _configure_cmake(self):
        if not self._cmake:
            self._cmake = CMake(self)
            self._cmake.configure()
        return self._cmake

    def build(self):
        for patch in self.conan_data.get("patches", {}).get(self.version, []):
            tools.patch(**patch)
        cmake = self._configure_cmake()
        cmake.build()

    def package(self):
        self.copy("LICENSE.txt", dst="licenses", src=self._source_subfolder)
        cmake = self._configure_cmake()
        cmake.install()
        tools.rmdir(os.path.join(self.package_folder, "lib", "cmake"))

    def package_info(self):
        self.cpp_info.names["cmake_find_package"] = "cppcoro"
        self.cpp_info.names["cmake_find_package_multi"] = "cppcoro"
        self.cpp_info.libs = ["cppcoro"]
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.cpp_info.system_libs.append("pthread")
        if self.settings.compiler == "Visual Studio":
            if tools.Version(self.settings.compiler.version) <= "15"):
                self.cpp_info.cxxflags.append("/await")
            self.cpp_info.cxxflags.append("/await:heapelide")
        elif self.settings.compiler == "gcc":
            self.cpp_info.cxxflags.append("-fcoroutines")
        elif self.settings.compiler == "clang" or self.settings.compiler == "apple-clang":
            self.cpp_info.cxxflags.append("-fcoroutines-ts")
