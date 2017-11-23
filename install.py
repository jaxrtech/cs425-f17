from setuptools import setup

setup(
    name='aero',
    packages=['aero'],
    include_package_data=True,
    install_requires=[
        'flask',
        'flask-bootstrap',
        'flask-sqlalchemy',
        'flask-login',
        'sqlalchemy'
    ]
)