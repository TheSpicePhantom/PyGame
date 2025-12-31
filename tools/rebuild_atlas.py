"""
Rebuild texture atlas from data/ definitions.
Tool für Entwickler zum manuellen Rebuild des Atlas.
"""
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from view.texture_collector import TextureCollector
from view.texture_atlas_builder import TextureAtlasBuilder


def rebuild_atlas():
    """Rebuild texture atlas from data/ definitions."""
    print("=== Rebuilding Texture Atlas ===")
    
    # 1. Collect textures from data/
    print("\n[1/3] Collecting textures from data/...")
    collector = TextureCollector()
    texture_refs = collector.collect_all_textures()
    
    # Save texture references cache
    collector.save_texture_list()
    print(f"  ✓ Collected {sum(len(v) for v in texture_refs.values())} textures")
    
    # 2. Build atlas
    print("\n[2/3] Building atlas...")
    builder = TextureAtlasBuilder()
    if not builder.build_atlas(texture_refs):
        print("  ✗ Failed to build atlas")
        return False
    
    print(f"  ✓ Atlas built: {builder.atlas_size}x{builder.atlas_size}")
    print(f"  ✓ Packed {len(builder.uv_map)} textures")
    
    # 3. Export
    print("\n[3/3] Exporting atlas...")
    builder.save_atlas()
    print("  ✓ Atlas exported to data/atlas.png")
    print("  ✓ UV map exported to data/atlas_uv_map.json")
    
    # Statistics
    print("\n=== Statistics ===")
    for category, textures in texture_refs.items():
        if textures:
            print(f"  {category}: {len(textures)} textures")
    print(f"  Total: {sum(len(v) for v in texture_refs.values())} textures")
    print(f"  Failed: {len(builder.failed_textures)} textures")
    
    print("\n=== Atlas Rebuilt! ===")
    return True


if __name__ == '__main__':
    try:
        success = rebuild_atlas()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nRebuild cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nError during rebuild: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
