import { V5StoryBlueprint, V5StorySection } from "./engine";

export function updateBlueprintSection(
  blueprint: V5StoryBlueprint,
  sectionId: string,
  updater: (section: V5StorySection) => V5StorySection,
): V5StoryBlueprint {
  return {
    ...blueprint,
    sections: updateSectionList(blueprint.sections || [], sectionId, updater),
    metadata: {
      ...(blueprint.metadata || {}),
      updated_at: new Date().toISOString(),
    },
  };
}

export function findSectionById(sections: V5StorySection[] | undefined, sectionId: string): V5StorySection | null {
  for (const section of sections || []) {
    if (section.section_id === sectionId) return section;
    const found = findSectionById(section.children || [], sectionId);
    if (found) return found;
  }
  return null;
}

export function withBlueprintMetadata(
  blueprint: V5StoryBlueprint,
  patch: NonNullable<V5StoryBlueprint["metadata"]>,
): V5StoryBlueprint {
  return {
    ...blueprint,
    metadata: {
      ...(blueprint.metadata || {}),
      ...patch,
      updated_at: new Date().toISOString(),
    },
  };
}

export function getAssetThumbnailPath(asset: unknown): string | null {
  if (!asset || typeof asset !== "object") return null;
  const maybeAsset = asset as { thumbnail_path?: unknown; thumbnail?: unknown };

  if (typeof maybeAsset.thumbnail_path === "string" && maybeAsset.thumbnail_path.length > 0) {
    return maybeAsset.thumbnail_path;
  }

  if (typeof maybeAsset.thumbnail === "string" && maybeAsset.thumbnail.length > 0) {
    return maybeAsset.thumbnail;
  }

  return null;
}

function updateSectionList(
  sections: V5StorySection[],
  sectionId: string,
  updater: (section: V5StorySection) => V5StorySection,
): V5StorySection[] {
  return sections.map((section) => {
    if (section.section_id === sectionId) {
      return updater(section);
    }
    return {
      ...section,
      children: updateSectionList(section.children || [], sectionId, updater),
    };
  });
}
