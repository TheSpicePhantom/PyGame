"""
Tool Mapping Registry: Central registry for tool hardness tiers and mining capabilities.
Supports hot-reload for development (F5 key).
"""
import json
import os
from typing import Dict, Optional, List
from pathlib import Path


class ToolMappingRegistry:
    """Central registry for tool hardness tiers and mining capabilities."""
    
    _tool_tiers: Dict[str, dict] = {}
    _hardness_levels: Dict[str, dict] = {}
    _tool_to_tier: Dict[str, str] = {}  # tool_id -> tier_name
    _diagnostics = None
    
    @classmethod
    def set_diagnostics(cls, diagnostics_service):
        """Set diagnostics service for logging."""
        cls._diagnostics = diagnostics_service
    
    @classmethod
    def _log(cls, level: str, message: str):
        """Log message with diagnostics or print fallback."""
        if cls._diagnostics:
            getattr(cls._diagnostics, level)("ToolMappingRegistry", message)
        else:
            print(f"[ToolMappingRegistry] {message}")
    
    @classmethod
    def load_all(cls, data_path: str = "data/mappings/tool_mapping.json"):
        """
        Load tool mapping from JSON file.
        
        Args:
            data_path: Path to tool_mapping.json file
        """
        cls._tool_tiers.clear()
        cls._hardness_levels.clear()
        cls._tool_to_tier.clear()
        
        if not os.path.exists(data_path):
            cls._log("warning", f"Tool mapping file does not exist: {data_path}")
            return
        
        try:
            with open(data_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # Load tool tiers
                tool_tiers = data.get('tool_tiers', {})
                for tier_name, tier_config in tool_tiers.items():
                    cls._tool_tiers[tier_name] = tier_config
                    
                    # Map tools to tier
                    tools = tier_config.get('tools', [])
                    for tool_id in tools:
                        cls._tool_to_tier[tool_id] = tier_name
                    
                    cls._log("debug", f"  Loaded tool tier: {tier_name} (tier: {tier_config.get('tier', 0)})")
                
                # Load hardness levels
                hardness_levels = data.get('hardness_levels', {})
                for hardness_name, hardness_config in hardness_levels.items():
                    cls._hardness_levels[hardness_name] = hardness_config
                    cls._log("debug", f"  Loaded hardness level: {hardness_name} (tier: {hardness_config.get('tier', 0)})")
                
                cls._log("info", f"Loaded {len(cls._tool_tiers)} tool tiers and {len(cls._hardness_levels)} hardness levels")
                
        except Exception as e:
            cls._log("error", f"Error loading tool mapping: {e}")
    
    @classmethod
    def reload(cls):
        """Reload tool mapping (for hot-reload with F5)."""
        cls._log("info", "Reloading tool mapping...")
        cls.load_all()
        cls._log("info", "Reload complete!")
    
    @classmethod
    def get_tool_level(cls, tool_id: str) -> Optional[str]:
        """
        Get tool tier name for a tool ID.
        
        Args:
            tool_id: Tool identifier (e.g., "tools:iron_axe")
            
        Returns:
            Tier name (e.g., "iron") or None if not found
        """
        return cls._tool_to_tier.get(tool_id)
    
    @classmethod
    def get_tool_tier(cls, tool_id: str) -> int:
        """
        Get numeric tier value for a tool ID.
        
        Args:
            tool_id: Tool identifier
            
        Returns:
            Tier value (0 = lowest) or 0 if not found
        """
        tier_name = cls.get_tool_level(tool_id)
        if tier_name:
            tier_config = cls._tool_tiers.get(tier_name, {})
            return tier_config.get('tier', 0)
        return 0
    
    @classmethod
    def get_mining_speed_multiplier(cls, tool_id: str) -> float:
        """
        Get mining speed multiplier for a tool ID.
        
        Args:
            tool_id: Tool identifier
            
        Returns:
            Mining speed multiplier (1.0 = normal speed) or 0.3 (hand default) if not found
        """
        tier_name = cls.get_tool_level(tool_id)
        if tier_name:
            tier_config = cls._tool_tiers.get(tier_name, {})
            return tier_config.get('mining_speed_multiplier', 0.3)
        # Default to hand speed if tool not found
        return 0.3
    
    @classmethod
    def get_hardness_tier(cls, hardness: str) -> int:
        """
        Get tier value for a hardness level.
        
        Args:
            hardness: Hardness level name (e.g., "wood", "iron")
            
        Returns:
            Tier value or 1 (wood default) if not found
        """
        hardness_config = cls._hardness_levels.get(hardness, {})
        return hardness_config.get('tier', 1)  # Default to wood tier
    
    @classmethod
    def can_mine(cls, tool_id: str, resource_hardness: str) -> bool:
        """
        Check if a tool can mine a resource with given hardness.
        
        Uses hybrid approach:
        1. Check explicit can_mine list (for modding flexibility)
        2. Check tier comparison (O(1), performant)
        
        Args:
            tool_id: Tool identifier
            resource_hardness: Resource hardness level
            
        Returns:
            True if tool can mine resource, False otherwise
        """
        # Get tool tier and mapping
        tool_level = cls.get_tool_level(tool_id)
        if not tool_level:
            # Tool not found, check if it's hand (default)
            # For now, assume hand can only mine wood
            if resource_hardness == 'wood':
                return True
            return False
        
        tool_mapping = cls._tool_tiers.get(tool_level)
        if not tool_mapping:
            return False
        
        # Method 1: Check explicit can_mine list (for modding flexibility)
        can_mine_list = tool_mapping.get('can_mine', [])
        if resource_hardness in can_mine_list:
            return True
        
        # Method 2: Check tier comparison (O(1), performant)
        tool_tier = tool_mapping.get('tier', 0)
        resource_tier_config = cls._hardness_levels.get(resource_hardness)
        if resource_tier_config:
            resource_tier = resource_tier_config.get('tier', 0)
            return tool_tier >= resource_tier
        
        return False  # Resource hardness not found
    
    @classmethod
    def get_level_mapping(cls, tier_name: str) -> Optional[dict]:
        """
        Get tool tier mapping by tier name.
        
        Args:
            tier_name: Tier name (e.g., "iron", "copper")
            
        Returns:
            Tier mapping dict or None if not found
        """
        return cls._tool_tiers.get(tier_name)
