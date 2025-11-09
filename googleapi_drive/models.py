"""Data models for Google Drive items."""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class ItemType(str, Enum):
    """Type of Drive item."""
    DIRECTORY = "directory"
    RAW_FILE = "raw_file"
    DOCS_DOCUMENT = "docs_document"
    DOCS_SLIDES = "docs_slides"
    DOCS_SHEETS = "docs_sheets"


def item_type_from_mime_type(mime_type: str) -> ItemType:
    """Convert Google Drive MIME type to ItemType enum."""
    if mime_type == 'application/vnd.google-apps.folder':
        return ItemType.DIRECTORY
    elif mime_type == 'application/vnd.google-apps.document':
        return ItemType.DOCS_DOCUMENT
    elif mime_type == 'application/vnd.google-apps.presentation':
        return ItemType.DOCS_SLIDES
    elif mime_type == 'application/vnd.google-apps.spreadsheet':
        return ItemType.DOCS_SHEETS
    else:
        return ItemType.RAW_FILE


@dataclass
class DriveItemPermission:
    """User permissions for a Drive item."""
    can_edit: bool
    can_comment: bool
    can_view: bool


class DriveItem:
    """Represents a Google Drive item (file, folder, or Google Workspace document)."""
    
    def __init__(self, id: str):
        self._id = id
        self._name = None
        self._created_time = None
        self._modified_time = None
        self._owner = None
        self._type = None
        self._properties = {}
        self._app_properties = {}
        self._permissions = []
        self._children_ids = []
        self._export_links = None
    
    @property
    def id(self) -> str:
        return self._id
    
    @property
    def name(self) -> str | None:
        return self._name
    
    @property
    def created_time(self) -> str | None:
        return self._created_time
    
    @property
    def modified_time(self) -> str | None:
        return self._modified_time
    
    @property
    def owner(self) -> str | None:
        return self._owner
    
    @property
    def type(self) -> ItemType | None:
        return self._type
    
    @property
    def permissions(self) -> list[DriveItemPermission]:
        return self._permissions.copy()
    
    @property
    def children_ids(self) -> list[str]:
        return self._children_ids.copy()
    
    @property
    def export_links(self) -> dict[str, str] | None:
        return self._export_links.copy() if self._export_links else None
    
    def populate(
        self,
        name: str | None = None,
        created_time: str | None = None,
        modified_time: str | None = None,
        owner: str | None = None,
        type: ItemType | None = None,
        properties: dict[str, str] | None = None,
        app_properties: dict[str, str] | None = None,
        permissions: list[DriveItemPermission] | None = None,
        children_ids: list[str] | None = None,
        export_links: dict[str, str] | None = None
    ) -> 'DriveItem':
        """
        Manually populate DriveItem fields.
        
        Args:
            name: File name
            created_time: Creation timestamp
            modified_time: Modification timestamp
            owner: Owner email address
            type: Item type
            properties: Global properties dictionary
            app_properties: App-specific properties dictionary
            permissions: List of permissions
            children_ids: List of child IDs (for directories only)
            export_links: Export links for Google Workspace documents (mimeType -> URL)
            
        Returns:
            Self for method chaining
        """
        if name is not None:
            self._name = name
        if created_time is not None:
            self._created_time = created_time
        if modified_time is not None:
            self._modified_time = modified_time
        if owner is not None:
            self._owner = owner
        if type is not None:
            self._type = type
        if properties is not None:
            self._properties = properties
        if app_properties is not None:
            self._app_properties = app_properties
        if permissions is not None:
            self._permissions = permissions
        if children_ids is not None:
            if self._type is not None and self._type != ItemType.DIRECTORY:
                raise ValueError("children_ids can only be set for DIRECTORY items")
            self._children_ids = children_ids
        if export_links is not None:
            self._export_links = export_links
        
        return self
    
    def get_properties(self, global_props: bool = False) -> dict[str, str]:
        """
        Get file properties.
        
        Args:
            global_props: If True, returns properties (global). If False, returns appProperties (app-specific)
            
        Returns:
            Dictionary of properties or appProperties
        """
        return self._properties.copy() if global_props else self._app_properties.copy()
    
    def update_from_api(self, file_info: dict) -> 'DriveItem':
        """
        Update this DriveItem from Google Drive API file info dictionary.
        
        Args:
            file_info: Dictionary from Google Drive API files().get() or files().list()
            
        Returns:
            Self for method chaining
        """
        self._name = file_info.get('name')
        self._created_time = file_info.get('createdTime')
        self._modified_time = file_info.get('modifiedTime')
        self._owner = file_info.get('owners', [{}])[0].get('emailAddress') if file_info.get('owners') else None
        self._type = item_type_from_mime_type(file_info.get('mimeType', ''))
        self._properties = file_info.get('properties', {})
        self._app_properties = file_info.get('appProperties', {})
        self._permissions = [DriveItemPermission(
            can_edit=file_info.get('capabilities', {}).get('canEdit', False),
            can_comment=file_info.get('capabilities', {}).get('canComment', False),
            can_view=file_info.get('capabilities', {}).get('canView', True)
        )]
        self._export_links = file_info.get('exportLinks')
        return self
    
    def to_dict(self) -> dict:
        """Convert DriveItem to dictionary."""
        return {
            'id': self._id,
            'name': self._name,
            'created_time': self._created_time,
            'modified_time': self._modified_time,
            'owner': self._owner,
            'type': self._type.value if self._type else None,
            'properties': self._properties.copy(),
            'app_properties': self._app_properties.copy(),
            'permissions': [
                {
                    'can_edit': p.can_edit,
                    'can_comment': p.can_comment,
                    'can_view': p.can_view
                }
                for p in self._permissions
            ],
            'children_ids': self._children_ids.copy() if self._children_ids is not None else None,
            'export_links': self._export_links.copy() if self._export_links else None
        }

