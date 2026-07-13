# Milestone 2A Design Decisions

1. The project document is a single aggregate root.
2. Metadata, canvas, transform, and layer descriptors are immutable value objects.
3. Active-layer selection is transient and does not affect dirty-state.
4. A newly created document is dirty until its first successful save.
5. Negative scales are permitted for future non-destructive mirroring.
6. Persistence is deferred to Milestone 2B and must consume the existing domain API.
