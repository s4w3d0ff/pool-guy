from setuptools import setup, find_packages

setup(
    name="poolguy",
    version="0.1.5",
    author="s4w3d0ff",
    author_email="",
    description="A Twitch bot framework with event subscription and alert handling capabilities",
    long_description=open("README.md", encoding="utf-8").read() if open("README.md", encoding="utf-8") else "",
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
        "aiohttp",         # async HTTP server
        "websockets",      # WebSocket client
        "python-dateutil", # date parsing
        "aiofiles"         # async file editing
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
