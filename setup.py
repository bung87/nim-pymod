#!/usr/bin/env python

from setuptools import setup, find_packages
import os,sys
import pkg_resources

version = '0.1.0'

extras_require = {
    "numpy": ["numpy >= 1.11.0"]
}


setup(
    name='nim_pm',
    version=version,
    description='',
    license='MIT',
    url='https://github.com/bung87/nim-pymod',
    packages=["nim_pm"],
    package_dir={'nim_pm': 'nim_pm'},
    entry_points={
        'console_scripts': [
            'pmgen=nim_pm:gen'
        ],
    },
    extras_require=extras_require,
    classifiers=[
        'Development Status :: 1 - Alpha',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
)