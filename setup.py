from setuptools import setup, find_packages

setup(
    name="pool-guy",
    version="0.1.0",
    author="s4w3d0ff",
    author_email="",  # Add if available
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
        "Topic :: Multimedia :: Sound/Audio",
        "Topic :: Communications :: Chat",
        "Framework :: AsyncIO",
    ],
    python_requires=">=3.10",  # Using 3.10+ due to match/case syntax
    install_requires=[
        "aiohttp",         # For async HTTP requests
        "websockets",      # For WebSocket connections
        "quart",           # For async web framework
        "python-dateutil", # For date parsing
        "beautifulsoup4",  # For HTML parsing (used in fetch_eventsub_types)
        "requests",        # For HTTP requests in fetch_eventsub_types
    ],
    extras_require={
        'mongodb': ['pymongo'],  # Optional MongoDB storage support
        'sqlite': ['aiosqlite'],  # Optional SQLite support
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