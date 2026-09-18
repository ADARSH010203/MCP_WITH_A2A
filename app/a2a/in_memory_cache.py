import streamlit as st
import threading
import time
from typing import Any, Dict, Optional

class InMemoryCache:
    _instance: Optional["InMemoryCache"] = None
    _lock: threading.Lock = threading.Lock()
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            with self._lock:
                if not self._initialized:
                    self._cache_data: Dict[str, Dict[str, Any]] = {}
                    self._ttl: Dict[str, float] = {}
                    self._data_lock: threading.Lock = threading.Lock()
                    self._initialized = True

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        with self._data_lock:
            self._cache_data[key] = value
            if ttl:
                self._ttl[key] = time.time() + ttl

    def get(self, key: str) -> Optional[Any]:
        with self._data_lock:
            if key in self._cache_data:
                if key in self._ttl:
                    if time.time() > self._ttl[key]:
                        del self._cache_data[key]
                        del self._ttl[key]
                        return None
                return self._cache_data[key]
            return None

    def delete(self, key: str) -> None:
        with self._data_lock:
            if key in self._cache_data:
                del self._cache_data[key]
            if key in self._ttl:
                del self._ttl[key]

# Streamlit UI
st.set_page_config(page_title="In-Memory Cache Manager", layout="wide")

st.title("🚀 In-Memory Cache Manager")
st.markdown("---")

# Initialize cache
cache = InMemoryCache()

# Sidebar
st.sidebar.header("Cache Operations")
operation = st.sidebar.selectbox(
    "Select Operation",
    ["Set Cache", "Get Cache", "Delete Cache"]
)

# Main content
col1, col2 = st.columns([2,1])

with col1:
    if operation == "Set Cache":
        st.subheader("Set Cache Value")
        key = st.text_input("Enter Key")
        value = st.text_area("Enter Value")
        ttl = st.number_input("Time to Live (seconds)", min_value=0, value=0)
        
        if st.button("Set Value", type="primary"):
            if key and value:
                cache.set(key, value, ttl if ttl > 0 else None)
                st.success(f"Successfully set value for key: {key}")
            else:
                st.error("Please enter both key and value")

    elif operation == "Get Cache":
        st.subheader("Get Cache Value")
        key = st.text_input("Enter Key to Retrieve")
        
        if st.button("Get Value", type="primary"):
            if key:
                value = cache.get(key)
                if value:
                    st.info("Retrieved Value:")
                    st.code(value)
                else:
                    st.warning("No value found for this key")
            else:
                st.error("Please enter a key")

    elif operation == "Delete Cache":
        st.subheader("Delete Cache Value")
        key = st.text_input("Enter Key to Delete")
        
        if st.button("Delete Value", type="primary"):
            if key:
                cache.delete(key)
                st.success(f"Successfully deleted key: {key}")
            else:
                st.error("Please enter a key")

with col2:
    st.subheader("Cache Status")
    with st.expander("Current Cache Contents"):
        st.json(cache._cache_data)
    
    with st.expander("TTL Status"):
        current_time = time.time()
        ttl_status = {k: v - current_time for k, v in cache._ttl.items()}
        st.json(ttl_status)

# Footer
st.markdown("---")
st.markdown("### How to Use")
st.markdown("""
- **Set Cache**: Add new key-value pairs with optional TTL
- **Get Cache**: Retrieve values using their keys
- **Delete Cache**: Remove key-value pairs from cache
""")
"""In Memory Cache utility."""

import threading
import time
from typing import Any, Dict, Optional


class InMemoryCache:
    """A thread-safe Singleton class to manage cache data.

    Ensures only one instance of the cache exists across the application.
    """

    _instance: Optional["InMemoryCache"] = None
    _lock: threading.Lock = threading.Lock()
    _initialized: bool = False

    def __new__(cls):
        """Override __new__ to control instance creation (Singleton pattern).

        Uses a lock to ensure thread safety during the first instantiation.

        Returns:
            The singleton instance of InMemoryCache.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize the cache storage.

        Uses a flag (_initialized) to ensure this logic runs only on the very first
        creation of the singleton instance.
        """
        if not self._initialized:
            with self._lock:
                if not self._initialized:
                    # print("Initializing SessionCache storage")
                    self._cache_data: Dict[str, Dict[str, Any]] = {}
                    self._ttl: Dict[str, float] = {}
                    self._data_lock: threading.Lock = threading.Lock()
                    self._initialized = True

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set a key-value pair.

        Args:
            key: The key for the data.
            value: The data to store.
            ttl: Time to live in seconds. If None, data will not expire.
        """
        with self._data_lock:
            self._cache_data[key] = value

            if ttl is not None:
                self._ttl[key] = time.time() + ttl
            else:
                if key in self._ttl:
                    del self._ttl[key]

    def get(self, key: str, default: Any = None) -> Any:
        """Get the value associated with a key.

        Args:
            key: The key for the data within the session.
            default: The value to return if the session or key is not found.

        Returns:
            The cached value, or the default value if not found.
        """
        with self._data_lock:
            if key in self._ttl and time.time() > self._ttl[key]:
                del self._cache_data[key]
                del self._ttl[key]
                return default
            return self._cache_data.get(key, default)

    def delete(self, key: str) -> None:
        """Delete a specific key-value pair from a cache.

        Args:
            key: The key to delete.

        Returns:
            True if the key was found and deleted, False otherwise.
        """

        with self._data_lock:
            if key in self._cache_data:
                del self._cache_data[key]
                if key in self._ttl:
                    del self._ttl[key]
                return True
            return False

    def clear(self) -> bool:
        """Remove all data.

        Returns:
            True if the data was cleared, False otherwise.
        """
        with self._data_lock:
            self._cache_data.clear()
            self._ttl.clear()
            return True
        return False
