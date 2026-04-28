from setuptools import setup, find_packages

setup(
    name='cmsspawner',
    version='0.0.1',

    packages=find_packages(),
    package_data={
        '': ['templates/*.jinja2']
    },

    author='gabenD',
    author_email='',
    description='Description of your library',

    classifiers=[
        'Programming Language :: Python :: 3',
    ],
)
