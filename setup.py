import pathlib
import re
from setuptools import find_packages, setup


here = pathlib.Path(__file__).parent
fname = here / "neuro_flow" / "__init__.py"


with fname.open(encoding="utf8") as fp:
    try:
        version = re.findall(r'^__version__ = "([^"]+)"$', fp.read(), re.M)[0]
    except IndexError:
        raise RuntimeError("Unable to determine version.")

setup(
    name="neuro-flow",
    version=version,
    description="Pipelines system for neu.ro",
    author="Neu.ro Team",
    author_email="team@neu.ro",
    license="Apache License, version 2.0",
    url="https://neu.ro/",
    python_requires=">=3.6.0",
    include_package_data=True,
    install_requires=[
        "neuro-cli>=21.5.17",
        "pyyaml>=5.4",
        "funcparserlib>=0.3",
        'dataclasses>=0.5; python_version<"3.7"',
        "humanize>=0.5.1",
        'backports-datetime-fromisoformat>=1.0.0; python_version<"3.7"',
        'async_exit_stack>=1.0.1; python_version<"3.7"',
        "neuro-extras>=20.12.16",
        "graphviz>=0.14",
        "yarl>=1.6.2,<1.7",
        "multidict>=5.0,<6.0",
        "rich~=10.0",
    ],
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
    entry_points={"console_scripts": ["neuro-flow=neuro_flow.cli:main"]},
)
