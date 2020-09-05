from setuptools import setup

version = '0.1.1'

setup(
    name='classroom_sync',
    version=version,
    url='https://github.com/TaylorSMarks/classroom_sync/',
    author='Taylor S. Marks',
    author_email='tayor@marksfam.com',
    description='A Thonny Plugin for easily sharing code in an online classroom.',
    packages = ['thonnycontrib'],
    platforms='any',
    install_requires=[
        'requests'
    ]
)
