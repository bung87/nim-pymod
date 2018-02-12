#!/usr/bin/env python

from setuptools import setup, find_packages
import os,sys
import pkg_resources

version = '0.1.0'

install_requires = [
    'numpy'
]


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
    install_requires=install_requires,
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