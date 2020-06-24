from setuptools import find_packages, setup


setup(
    name="neuro-flow",
    description="Pipelines system for neu.ro",
    author="Neuromation Team",
    author_email="pypi@neuromation.io",  # TODO: change this email
    license="Apache License, version 2.0",
    url="https://neu.ro/",
    python_requires=">=3.6.0",
    install_requires=["neuromation>=20.6.23", "pyyaml>=5.3", "trafaret>=2.0.2"],
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "Intended Audience :: Information Technology",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Software Development",
        "Topic :: Utilities",
        "License :: OSI Approved :: Apache Software License",
    ],
)
