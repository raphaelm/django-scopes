from codecs import open
from os import path

from setuptools import find_packages, setup

here = path.abspath(path.dirname(__file__))

with open('README.md') as fh:
    long_description = fh.read()

try:
    from django_scopes import version
except ImportError:
    version = '?'

setup(
    name='django-scopes',
    version=version,
    description='Scope querys in multi-tenant django applications',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/raphaelm/django-scopes',
    author='Raphael Michel',
    author_email='mail@raphaelmichel.de',
    license='Apache License 2.0',
    classifiers=[
        'Intended Audience :: Developers',
        'Intended Audience :: Other Audience',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Framework :: Django :: 2.1',
        'Framework :: Django :: 2.2',
    ],

    keywords='json database models',
    install_requires=[
    ],

    packages=find_packages(exclude=['tests', 'tests.*', 'demoproject', 'demoproject.*']),
    include_package_data=True,
)
