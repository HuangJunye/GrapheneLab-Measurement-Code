import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="gcodes",
    version="0.1.0",
    author="Eoin O'Farrel, Huang Junye",
    author_email="h.jun.ye@gmail.com",
    description="Simple-to-use low temperature transport measurement code",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/HuangJunye/GrapheneLab-Measurement-Code",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache 2.0 Licence",
        "Operating System :: OS Independent",
    ],
)