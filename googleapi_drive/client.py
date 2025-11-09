"""Google Drive API v3 client."""

from typing import List, Optional
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io
from datetime import datetime

from .models import DriveItem, ItemType

import logging
logger = logging.getLogger(__name__)


class DriveClient:
    """
    Client for Google Drive API v3.
    
    Handles Drive operations: listing, searching, downloading, comments, properties, labels.
    """
    
    def __init__(self, credentials):
        """
        Initialize the Drive API client.
        
        Args:
            credentials: Google OAuth2 credentials object with get_credentials() method
                        or a Credentials object directly
        """
        # Support both OAuth2Client objects and raw Credentials
        if hasattr(credentials, 'get_credentials'):
            self.service = build('drive', 'v3', credentials=credentials.get_credentials())
        else:
            self.service = build('drive', 'v3', credentials=credentials)
        
        # Get Client User Information
        result = self.service.about().get(fields="user").execute()
        if not 'user' in result:
            raise ValueError("User information not found")
        self.user_id = result['user']['permissionId']
        self.user_name = result['user']['displayName']
        self.user_email = result['user']['emailAddress']
        self.drives = self.get_drives_info()

    def get_user_info(self) -> dict:
        """Get current user information."""
        return {
            'id': self.user_id,
            'name': self.user_name,
            'email': self.user_email
        }

    def get_drives_info(self) -> List[DriveItem]:
        """
        List My Drive and all Shared Drives accessible to the client user.
        
        Returns:
            List of DriveItem objects for each accessible drive.
            First item is always My Drive.
        """
        self.drives = []
        
        # Get My Drive - use 'root' as the ID (standard for user's personal drive)
        root_drive = DriveItem(id='root')
        root_drive.populate(name='My Drive')
        self.drives.append(root_drive)
        
        # List all Shared Drives
        try:
            shared_drives = self.service.drives().list().execute()
            for drive in shared_drives.get('drives', []):
                self.drives.append(DriveItem(id=drive['id']))
        except Exception:
            # If the user doesn't have access to Shared Drives API or no shared drives exist
            pass
        
        return self.drives

    def get_item(self, item_id: str) -> DriveItem:
        """
        Fetch a DriveItem by ID from Google Drive API.
        
        Args:
            item_id: The ID of the item to fetch
            
        Returns:
            Fully populated DriveItem
            
        Raises:
            ValueError: If the file is not found or the API call fails
        """
        try:
            file_info = self.service.files().get(
                fileId=item_id,
                fields='id, name, createdTime, modifiedTime, mimeType, kind, capabilities, owners, appProperties, properties, exportLinks',
                supportsAllDrives=True
            ).execute()
            
            if not file_info:
                raise ValueError(f"File with ID '{item_id}' not found")
            
            item = DriveItem(id=item_id)
            return item.update_from_api(file_info)
        except Exception as e:
            raise ValueError(f"Failed to fetch file '{item_id}': {str(e)}") from e

    def list_items(self, parent_id: str, limit: int = None) -> List[DriveItem]:
        """
        List all items in a directory with pagination support.
        
        Args:
            parent_id: The ID of the parent directory
            limit: Optional maximum number of items to return. If None, returns all items.
            
        Returns:
            List of fully populated DriveItem objects
            
        Note:
            This method handles pagination automatically, fetching all pages until
            no more results exist or the limit is reached.
        """
        drive_items = []
        page_token = None
        page_size = min(1000, limit) if limit else 1000  # API max is 1000
        
        while True:
            # Build request parameters
            request_params = {
                'q': f"'{parent_id}' in parents and trashed=false",
                'fields': 'nextPageToken, files(id, name, createdTime, modifiedTime, mimeType, kind, capabilities, owners, appProperties, properties)',
                'supportsAllDrives': True,
                'includeItemsFromAllDrives': True,
                'pageSize': page_size
            }
            
            if page_token:
                request_params['pageToken'] = page_token
            
            # Execute request
            response = self.service.files().list(**request_params).execute()
            items = response.get('files', [])
            
            # Process items
            for item_data in items:
                if limit and len(drive_items) >= limit:
                    return drive_items
                    
                item = DriveItem(id=item_data['id'])
                item.update_from_api(item_data)
                drive_items.append(item)
            
            # Check for next page
            page_token = response.get('nextPageToken')
            if not page_token:
                break
                
            # Adjust page size for next request if we're near the limit
            if limit:
                remaining = limit - len(drive_items)
                if remaining <= 0:
                    break
                page_size = min(1000, remaining)
        
        return drive_items
    
    def _collect_folder_ids_recursive(self, folder_id: str, visited: set = None) -> List[str]:
        """
        Recursively collect all folder IDs under a given folder (including the folder itself).
        
        Args:
            folder_id: The root folder ID to start from
            visited: Set of already visited folder IDs to prevent cycles
            
        Returns:
            List of all folder IDs including the root folder and all subfolders
        """
        if visited is None:
            visited = set()
        
        # Prevent circular references
        if folder_id in visited:
            return []
        
        visited.add(folder_id)
        folder_ids = [folder_id]
        
        try:
            # List all items in this folder
            items = self.list_items(folder_id)
            
            # Recursively collect subfolder IDs
            for item in items:
                if item.type == ItemType.DIRECTORY:
                    subfolder_ids = self._collect_folder_ids_recursive(item.id, visited)
                    folder_ids.extend(subfolder_ids)
        except Exception as e:
            logger.warning(f"Failed to list items in folder {folder_id}: {e}")
        
        return folder_ids
    
    def search_by_name(
        self,
        query: str,
        limit: int = 25,
        folder_id: Optional[str] = None
    ) -> List[DriveItem]:
        """
        Search for files by name across all drives (My Drive + Shared Drives).
        
        Args:
            query: Search query string to match against file names
            limit: Maximum number of results to return (default: 25)
            folder_id: Optional folder ID to restrict search to this folder and its subfolders
            
        Returns:
            List of DriveItem objects matching the search criteria
            
        Example:
            >>> client = DriveClient(...)
            >>> results = client.search_by_name("meeting notes", limit=10)
            >>> for item in results:
            ...     print(f"{item.name} ({item.id})")
        """
        # Escape single quotes in query
        escaped_query = query.replace("'", "\\'")
        
        # Build base query
        search_query = f"name contains '{escaped_query}' and trashed=false"
        
        # Add folder restriction if specified
        if folder_id:
            logger.info(f"Collecting folder IDs for recursive search under {folder_id}")
            folder_ids = self._collect_folder_ids_recursive(folder_id)
            logger.info(f"Found {len(folder_ids)} folders to search in")
            
            # Build OR clause for all folders
            if folder_ids:
                escaped_folder_ids = [fid.replace("'", "\\'") for fid in folder_ids]
                folder_clauses = " or ".join([f"'{fid}' in parents" for fid in escaped_folder_ids])
                search_query = f"({search_query}) and ({folder_clauses})"
        
        logger.info(f"Searching by name: '{query}' (limit={limit})")
        
        # Execute search with pagination
        drive_items = []
        page_token = None
        page_size = min(1000, limit)
        
        while True:
            # Build request parameters
            request_params = {
                'q': search_query,
                'fields': 'nextPageToken, files(id, name, createdTime, modifiedTime, mimeType, kind, capabilities, owners, appProperties, properties)',
                'supportsAllDrives': True,
                'includeItemsFromAllDrives': True,
                'pageSize': page_size
            }
            
            if page_token:
                request_params['pageToken'] = page_token
            
            # Execute request
            response = self.service.files().list(**request_params).execute()
            items = response.get('files', [])
            
            # Process items
            for item_data in items:
                if len(drive_items) >= limit:
                    logger.info(f"Search by name returned {len(drive_items)} results")
                    return drive_items
                    
                item = DriveItem(id=item_data['id'])
                item.update_from_api(item_data)
                drive_items.append(item)
            
            # Check for next page
            page_token = response.get('nextPageToken')
            if not page_token:
                break
                
            # Adjust page size for next request if we're near the limit
            remaining = limit - len(drive_items)
            if remaining <= 0:
                break
            page_size = min(1000, remaining)
        
        logger.info(f"Search by name returned {len(drive_items)} results")
        return drive_items
    
    def search_by_content(
        self,
        query: str,
        limit: int = 25,
        folder_id: Optional[str] = None
    ) -> List[DriveItem]:
        """
        Search for files by full-text content across all drives (My Drive + Shared Drives).
        
        Args:
            query: Search query string to match against file contents
            limit: Maximum number of results to return (default: 25)
            folder_id: Optional folder ID to restrict search to this folder and its subfolders
            
        Returns:
            List of DriveItem objects matching the search criteria
            
        Note:
            Full-text search works for Google Docs, Sheets, Slides, and some binary formats.
            Not all file types support content search.
            
        Example:
            >>> client = DriveClient(...)
            >>> results = client.search_by_content("quarterly revenue", limit=10)
            >>> for item in results:
            ...     print(f"{item.name} ({item.id})")
        """
        # Escape single quotes in query
        escaped_query = query.replace("'", "\\'")
        
        # Build base query
        search_query = f"fullText contains '{escaped_query}' and trashed=false"
        
        # Add folder restriction if specified
        if folder_id:
            logger.info(f"Collecting folder IDs for recursive search under {folder_id}")
            folder_ids = self._collect_folder_ids_recursive(folder_id)
            logger.info(f"Found {len(folder_ids)} folders to search in")
            
            # Build OR clause for all folders
            if folder_ids:
                escaped_folder_ids = [fid.replace("'", "\\'") for fid in folder_ids]
                folder_clauses = " or ".join([f"'{fid}' in parents" for fid in escaped_folder_ids])
                search_query = f"({search_query}) and ({folder_clauses})"
        
        logger.info(f"Searching by content: '{query}' (limit={limit})")
        
        # Execute search with pagination
        drive_items = []
        page_token = None
        page_size = min(1000, limit)
        
        while True:
            # Build request parameters
            request_params = {
                'q': search_query,
                'fields': 'nextPageToken, files(id, name, createdTime, modifiedTime, mimeType, kind, capabilities, owners, appProperties, properties)',
                'supportsAllDrives': True,
                'includeItemsFromAllDrives': True,
                'pageSize': page_size
            }
            
            if page_token:
                request_params['pageToken'] = page_token
            
            # Execute request
            response = self.service.files().list(**request_params).execute()
            items = response.get('files', [])
            
            # Process items
            for item_data in items:
                if len(drive_items) >= limit:
                    logger.info(f"Search by content returned {len(drive_items)} results")
                    return drive_items
                    
                item = DriveItem(id=item_data['id'])
                item.update_from_api(item_data)
                drive_items.append(item)
            
            # Check for next page
            page_token = response.get('nextPageToken')
            if not page_token:
                break
                
            # Adjust page size for next request if we're near the limit
            remaining = limit - len(drive_items)
            if remaining <= 0:
                break
            page_size = min(1000, remaining)
        
        logger.info(f"Search by content returned {len(drive_items)} results")
        return drive_items
    
    def update_properties(
        self,
        item: DriveItem,
        properties: dict[str, str],
        global_props: bool = False
    ) -> DriveItem:
        """
        Update file properties via Google Drive API.
        
        Args:
            item: The DriveItem to update
            properties: Dictionary of properties to set
            global_props: If True, updates properties (global). If False, updates appProperties (app-specific)
            
        Returns:
            Updated DriveItem (refreshed from API)
            
        Raises:
            ValueError: If the update fails
        """
        try:
            # Filter None values - those need to be explicitly deleted
            props_to_set = {k: v for k, v in properties.items() if v is not None}
            props_to_delete = [k for k, v in properties.items() if v is None]
            
            update_body = {}
            prop_key = 'properties' if global_props else 'appProperties'
            
            # Set non-None properties
            if props_to_set:
                update_body[prop_key] = props_to_set
            
            self.service.files().update(
                fileId=item.id,
                body=update_body,
                fields='id',
                supportsAllDrives=True
            ).execute()
            
            # Delete None properties separately
            for prop in props_to_delete:
                delete_body = {prop_key: {prop: None}}
                self.service.files().update(
                    fileId=item.id,
                    body=delete_body,
                    fields='id',
                    supportsAllDrives=True
                ).execute()
            
            # Refresh and return updated item
            return self.get_item(item.id)
        except Exception as e:
            raise ValueError(f"Failed to update properties for file '{item.id}': {str(e)}") from e

    def download_file(
        self,
        item: DriveItem,
        filesystem_path: Optional[str] = None
    ) -> Optional[bytes]:
        """
        Download raw binary data from a Drive file.
        
        Args:
            item: The DriveItem to download
            filesystem_path: Optional path to save file on disk. If None, returns bytes in memory.
            
        Returns:
            bytes if filesystem_path is None, otherwise None (file saved to disk)
            
        Raises:
            ValueError: If item is a Google Docs type or directory, or download fails
        """
        # Check if item is a directory or Google Docs type
        if item.type == ItemType.DIRECTORY:
            raise ValueError(f"Cannot download directory: {item.name}")
        
        if item.type in [ItemType.DOCS_DOCUMENT, ItemType.DOCS_SLIDES, ItemType.DOCS_SHEETS]:
            raise ValueError(f"Cannot download Google Docs type: {item.type.value}. Use export instead.")
        
        try:
            # Request file download
            request = self.service.files().get_media(fileId=item.id, supportsAllDrives=True)
            
            # Download to memory buffer
            file_buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(file_buffer, request)
            
            done = False
            while not done:
                status, done = downloader.next_chunk()
            
            # Get the binary data
            file_buffer.seek(0)
            binary_data = file_buffer.read()
            
            # Save to disk or return bytes
            if filesystem_path:
                with open(filesystem_path, 'wb') as f:
                    f.write(binary_data)
                return None
            else:
                return binary_data
                
        except Exception as e:
            raise ValueError(f"Failed to download file '{item.id}': {str(e)}") from e

    def get_comments(self, file_id: str) -> List[dict]:
        """
        Get all comments for a file.
        
        Args:
            file_id: The file ID
            
        Returns:
            List of comment dictionaries with formatted timestamps
        """
        try:
            comments = []
            page_token = None
            
            while True:
                response = self.service.comments().list(
                    fileId=file_id,
                    fields='nextPageToken, comments(id, content, author(displayName, emailAddress), createdTime, modifiedTime, quotedFileContent, replies(id, content, author(displayName, emailAddress), createdTime, modifiedTime), resolved, anchor)',
                    pageToken=page_token,
                    includeDeleted=False
                ).execute()
                
                comments.extend(response.get('comments', []))
                
                page_token = response.get('nextPageToken')
                if not page_token:
                    break
            
            logger.info(f"Retrieved {len(comments)} comments for file {file_id}")
            
            # Format comments and replies
            formatted_comments = []
            for comment in comments:
                # Format the comment time to be YYYY-MM-DD HH:MM
                created_dt = datetime.fromisoformat(comment['createdTime'].replace('Z', '+00:00'))
                modified_dt = datetime.fromisoformat(comment['modifiedTime'].replace('Z', '+00:00'))
                author_obj = comment.get('author', {})
                formatted_comment = {
                    'id': comment['id'],
                    'author': author_obj.get('displayName', 'Unknown'),
                    'author_email': author_obj.get('emailAddress', ''),
                    'content': comment.get('content', ''),
                    'snippet': comment.get('quotedFileContent', {}).get('value', ''),
                    'createdTime': created_dt.strftime('%Y-%m-%d %H:%M'),
                    'modifiedTime': modified_dt.strftime('%Y-%m-%d %H:%M'),
                    'resolved': comment.get('resolved', False),
                    'anchor': comment.get('anchor', ''),
                    'replies': []
                }
                for reply in comment.get('replies', []):
                    # Format these to be YYYY-MM-DD HH:MM
                    reply_created_dt = datetime.fromisoformat(reply['createdTime'].replace('Z', '+00:00'))
                    reply_modified_dt = datetime.fromisoformat(reply['modifiedTime'].replace('Z', '+00:00'))
                    reply_author_obj = reply.get('author', {})
                    formatted_comment['replies'].append({
                        'id': reply['id'],
                        'author': reply_author_obj.get('displayName', 'Unknown'),
                        'author_email': reply_author_obj.get('emailAddress', ''),
                        'content': reply.get('content', ''),
                        'createdTime': reply_created_dt.strftime('%Y-%m-%d %H:%M'), 
                        'modifiedTime': reply_modified_dt.strftime('%Y-%m-%d %H:%M'),
                    })
                formatted_comments.append(formatted_comment)
            return formatted_comments
        except Exception as e:
            logger.error(f"Error getting comments for file {file_id}: {e}")
            # Return empty list if comments API fails (some files don't support comments)
            return []

    def reply_to_comment(self, file_id: str, comment_id: str, content: str) -> dict:
        """
        Reply to a comment.
        
        Args:
            file_id: The file ID
            comment_id: The comment ID
            content: The content of the reply
            
        Returns:
            Response dict with reply ID
            
        Raises:
            ValueError: If the reply fails
        """
        try:
            response = self.service.replies().create(
                fileId=file_id,
                commentId=comment_id,
                body={'content': content},
                fields='id'
            ).execute()
            return response
        except Exception as e:
            raise ValueError(f"Failed to reply to comment {comment_id} for file {file_id}: {str(e)}") from e

    def check_item_access(self, item_id: str) -> bool:
        """
        Check if the current user has access to a file.
        
        Args:
            item_id: The item ID to check
            
        Returns:
            True if accessible, False otherwise
        """
        try:
            self.service.files().get(fileId=item_id, supportsAllDrives=True).execute()
            return True
        except Exception:
            return False

    def get_labels(self, item_id: str) -> List[dict]:
        """
        Get the labels applied to a file.
        
        Args:
            item_id: The item ID
            
        Returns:
            List of labels applied to the file
            
        Raises:
            ValueError: If the request fails
        """
        try:
            response = self.service.files().listLabels(fileId=item_id).execute()
            return response.get('labels', [])
        except Exception as e:
            raise ValueError(f"Failed to get labels for item {item_id}: {str(e)}") from e

