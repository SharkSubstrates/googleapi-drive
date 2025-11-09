# googleapi-drive

Google Drive API v3 client for Python.

## Overview

Clean, standalone client for Google Drive API v3. List files, search, download, manage properties and comments.

## Installation

```bash
pip install googleapi-drive
```

## Usage

```python
from googleapi_oauth import OAuth2Client
from secretstore import KeyringStorage
from googleapi_drive import DriveClient

# Authenticate
auth = OAuth2Client(
    client_id='your-client-id',
    client_secret='your-client-secret',
    scopes=['https://www.googleapis.com/auth/drive'],
    storage=KeyringStorage('myapp')
)

# Create Drive client
drive = DriveClient(auth)

# List files in My Drive
for item in drive.list_items('root'):
    print(f"{item.name} - {item.type.value}")

# Search by name
results = drive.search_by_name("meeting notes", limit=10)

# Search by content
results = drive.search_by_content("quarterly revenue", limit=10)

# Get file details
item = drive.get_item('file_id')
print(f"Owner: {item.owner}")
print(f"Created: {item.created_time}")

# Download a file
data = drive.download_file(item)  # Returns bytes
# or save to disk
drive.download_file(item, filesystem_path='/path/to/save')

# Update properties
drive.update_properties(item, {'key': 'value'})

# Get comments
comments = drive.get_comments('file_id')
for comment in comments:
    print(f"{comment['author']}: {comment['content']}")
```

## Features

- **List & Search**: List directory contents, search by name or full-text
- **Download**: Download binary files  
- **Properties**: Read and update file properties
- **Comments**: Get comments and replies, post replies
- **Drives**: Access My Drive and Shared Drives
- **Metadata**: File owners, timestamps, permissions

## API Reference

### DriveClient

#### `__init__(credentials)`
Initialize with OAuth2 credentials.

**Parameters:**
- `credentials`: OAuth2Client or Credentials object

#### `get_user_info() -> dict`
Get current user information.

#### `get_drives_info() -> List[DriveItem]`
List all accessible drives (My Drive + Shared Drives).

#### `get_item(item_id: str) -> DriveItem`
Fetch a single file/folder by ID.

#### `list_items(parent_id: str, limit: int = None) -> List[DriveItem]`
List contents of a directory.

#### `search_by_name(query: str, limit: int = 25, folder_id: Optional[str] = None) -> List[DriveItem]`
Search files by name.

#### `search_by_content(query: str, limit: int = 25, folder_id: Optional[str] = None) -> List[DriveItem]`
Full-text search across file contents.

#### `download_file(item: DriveItem, filesystem_path: Optional[str] = None) -> Optional[bytes]`
Download a file (not Google Workspace docs).

#### `update_properties(item: DriveItem, properties: dict, global_props: bool = False) -> DriveItem`
Update file properties.

#### `get_comments(file_id: str) -> List[dict]`
Get all comments for a file.

#### `reply_to_comment(file_id: str, comment_id: str, content: str) -> dict`
Reply to a comment.

### Models

#### `DriveItem`
Represents a Drive file, folder, or Google Workspace document.

**Properties:**
- `id`: File ID
- `name`: File name
- `type`: ItemType enum (DIRECTORY, RAW_FILE, DOCS_DOCUMENT, etc.)
- `created_time`: Creation timestamp
- `modified_time`: Last modified timestamp
- `owner`: Owner email
- `permissions`: List of DriveItemPermission objects

#### `ItemType`
Enum for file types:
- `DIRECTORY`
- `RAW_FILE`
- `DOCS_DOCUMENT`
- `DOCS_SLIDES`
- `DOCS_SHEETS`

## License

MIT

