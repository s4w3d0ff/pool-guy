from setuptools import setup, find_packages

setup(
    name="pool-guy",
    version="0.1.0",
    author="s4w3d0ff",
    author_email="",
    description="A Twitch bot framework with event subscription and alert handling capabilities",
    long_description=open("README.md").read() if open("README.md") else "",
    long_description_content_type="text/markdown",
    url="https://github.com/s4w3d0ff/pool-guy",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: OS Independent",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
        "Topic :: Communications :: Chat",
        "Framework :: AsyncIO"
    ],
    python_requires=">=3.10",
    install_requires=[
        "aiohttp>=3.8.0",      # For async HTTP requests and server
        "websockets>=10.0",     # For WebSocket client connections
        "python-dateutil>=2.8.2", # For date parsing
    ],
    extras_require={
        'mongodb': ['pymongo'],  # Optional MongoDB storage support
        'sqlite': ['aiosqlite']  # Optional SQLite support
    },
    zip_safe=False,
    license="GNU General Public License v3 (GPLv3)",
    platforms=["any"],
    keywords=[
        "twitch",
        "bot",
        "eventsub",
        "websocket",
        "async",
        "alerts",
        "streaming",
        "poolguy"
    ]
)