from conans import ConanFile, tools
import os

class TestPackageConan(ConanFile):
    settings = "os", "arch", "compiler", "build_type"

    def test(self):
        if not tools.cross_building(self):
            self.run("gfortran --version", run_environment=True)
            source_path = os.path.join(self.source_folder, "test_package.f")
            bin_path = os.path.join("bin", "test_package")
            self.run("gfortran {0} -o {1}".format(source_path, bin_path), run_environment=True)
