# Multi-workspace product boundary

The UI demonstrates workspace-aware organization, not backend multi-tenancy.

- **Northstar Commerce / Live Demo** is the IsoPact demo workspace. Its `ORD-8472` case is the canonical recorded case and is the only UI surface that presents the backed activity, evidence, Case Map, and receipt.
- **Acme Retail** and **Contoso Logistics** are explicitly marked synthetic workspace fixtures. They exist to exercise navigation, filtering, and queue hierarchy without implying isolated customer data, live integrations, settlement authority, or workspace-specific evidence.
- Queue metrics in the Demo workspace are fixture-derived. Integration status text states the actual scope of each adapter, and platform marks do not by themselves assert a connection.

This boundary is intentionally visible in the product UI so a reviewer can distinguish product-shell capability from proven backend behavior.
