from conans import ConanFile


class VirtualjpegConan(ConanFile):
    name = "virtual-libjpeg"
    description = "Virtual package to choose jpeg encoder/decoder implementation in final package."
    topics = ("conan", "virtual", "proxy", "image", "format", "jpg", "jpeg", "picture", "multimedia", "graphics")
    url = "https://github.com/conan-io/conan-center-index"

    options = {
        "provider": ["libjpeg", "libjpeg-turbo", "mozjpeg"],
    }
    default_options = {
        "provider": "libjpeg-turbo",
    }

    def requirements(self):
        if self.options.provider == "libjpeg":
            self.requires("libjpeg/9d")
        elif self.options.provider == "libjpeg-turbo":
            self.requires("libjpeg-turbo/2.0.5")
        else: #if self.options.provider == "mozjpeg":
            self.requires("mozjpeg/3.3.1")

    def package_id(self):
        self.info.header_only()

    def package_info(self):
        self.cpp_info.names["cmake_find_package"] = "JPEG"
        self.cpp_info.names["cmake_find_package_multi"] = "JPEG"
        self.cpp_info.names["pkg_config"] = "libjpeg"
        self.cpp_info.includedirs = []
        self.cpp_info.libdirs = []
        self.cpp_info.resdirs = []
        self.cpp_info.bindirs = []
        self.cpp_info.frameworkdirs = []
