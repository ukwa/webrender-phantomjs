from setuptools import setup, find_packages

with open('requirements.txt') as f:
    requirements = f.read().splitlines()

setup(
    name='webrender-phantomjs',
    version='2.0.0',
    packages=find_packages(),
    install_requires=requirements,
    include_package_data=True,

    license='Apache 2.0',
    long_description=open('README.md').read(),
)
