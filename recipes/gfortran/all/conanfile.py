from conans import ConanFile, tools
from conans.errors import ConanInvalidConfiguration
import os
import glob


required_conan_version = ">=1.32.0"


class GFortranConan(ConanFile):
    name = "gfortran"
    description = "The Fortran compiler front end and run-time libraries for GCC"
    url = "https://github.com/conan-io/conan-center-index"
    homepage = "https://gcc.gnu.org/fortran"
    topics = ("gnu", "gcc", "fortran", "compiler")
    license = "GPL-3.0-or-later"
    settings = "os", "arch"
    no_copy_source = True

    @property
    def _source_subfolder(self):
        return "source_subfolder"

    def validate(self):
        if self.settings.arch != "x86_64":
            raise ConanInvalidConfiguration("No binaries available for the architecture '{}'.".format(self.settings.arch))
        the_os = str(self.settings.os)
        if the_os not in self.conan_data["sources"][self.version]["url"]:
            raise ConanInvalidConfiguration("No binaries available for {0}".format(the_os))

    def build_requirements(self):
        if self.settings.os == "Windows":
            self.build_requires("7zip/19.00")

    def build(self):
        the_os = str(self.settings.os)
        url = self.conan_data["sources"][self.version]["url"][the_os]
        sha256 = self.conan_data["sources"][self.version]["sha256"][the_os]
        if the_os == "Windows":
            filename = os.path.basename(url)
            tools.download(url, filename, sha256=sha256)
            self.run("7z x {}".format(filename))
            os.remove(filename)
            extracted_dir = "mingw64"
        else:
            tools.get(url, sha256=sha256)
            extracted_dir = glob.glob("gcc-*")[0] if the_os == "Linux" else os.path.join("usr", "local")
        os.rename(extracted_dir, self._source_subfolder)

    def _extract_license(self):
        info = tools.load(os.path.join(self._source_subfolder, "share", "info", "gfortran.info"))
        license_contents = info[info.find("Version 3"):info.find("END OF TERMS", 1)]
        return license_contents

    def package(self):
        tools.save(os.path.join(self.package_folder, "licenses", "LICENSE"), self._extract_license())
        self.copy("gfortran*", dst="bin", src=os.path.join(self._source_subfolder, "bin"))
        self.copy("f951", dst="bin", src=os.path.join(self._source_subfolder, "libexec", "gcc", "x86_64-apple-darwin19", "10.2.0"))
        self.copy("libgfortran.a", dst="lib", src=os.path.join(self._source_subfolder, "lib64"))
        self.copy("libgfortran.a", dst="lib", src=os.path.join(self._source_subfolder, "lib"))
        self.copy("libgfortran.a", dst="lib", src=os.path.join(self._source_subfolder, "lib", "gcc", "x86_64-w64-mingw32", "10.2.0"))

    def package_info(self):
        bin_path = os.path.join(self.package_folder, "bin")
        self.output.info("Appending PATH environment variable: {}".format(bin_path))
        self.env_info.PATH.append(bin_path)
        self.cpp_info.libs = ["gfortran"]
