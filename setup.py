from setuptools import setup
from Cython.Build import cythonize

setup(
    ext_modules=cythonize([
        "MainFirmwareFlash.py",
        "FirmwareFlash.py",
        "firmware_version_integration.py",
        "SmartManufacturingSuite.py"
    ])
)
