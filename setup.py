from setuptools import find_packages, setup

setup(
    name="pool_manager",
    version="0.0.1",
    author="Your name",
    author_email="your@email.com",
    license="Proprietary License",
    platforms="all",
    python_requires=">=3.9",
    packages=find_packages(exclude=["tests"]),
    install_requires=[
        "aiopg~=1.2.1",
    ],
    extras_require={"dev": [
        "aiomisc~=14.1.0",
        "pytest~=6.2.4",
    ]},
)
