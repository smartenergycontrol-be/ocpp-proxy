from setuptools import setup, find_packages

setup(
    name="ocpp-proxy",
    version="0.1.0",
    description="OCPP 1.6 & 2.0.1 JSON WebSocket proxy for EV charger sharing",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.9",
    install_requires=[
        "ocpp>=2.0.0",
        "aiohttp>=3.9.0",
        "websockets>=12.0",
        "PyYAML>=6.0.0",
    ],
    extras_require={
        "test": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "pytest-aiohttp>=1.0.0",
            "pytest-mock>=3.12.0",
            "pytest-cov>=4.1.0",
            "aioresponses>=0.7.0",
        ]
    },
    entry_points={
        "console_scripts": [
            "ocpp-proxy=ocpp_proxy.main:main",
        ],
    },
)