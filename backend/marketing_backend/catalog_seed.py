from .product_lines import default_id
"""Restore the documented LorrySystem starter catalog into one native workspace."""

import argparse

from sqlalchemy import select

from .db import Session
from .models import Catalog, Workspace


ITEMS = (
    {
        "kind": "PRODUCT",
        "code": "AI_DASHCAM",
        "name": "AI Dashcams and Driver Safety Monitoring",
        "description": (
            "ADAS road-safety alerts; driver-monitoring alerts for fatigue and "
            "distraction; two-channel and four-channel camera configurations; "
            "incident photos and videos. Intended use includes driver-safety "
            "monitoring and incident evidence. Establish the prospect's current "
            "system and specific unmet need before proposing a change."
        ),
        "rules": {"intended_use": "Driver-safety monitoring and incident evidence"},
    },
    {
        "kind": "PRODUCT",
        "code": "GPS",
        "name": "GPS Tracking and Fleet Telematics",
        "description": (
            "Vehicle location, journey history, overspeed alerts, driving-event "
            "monitoring and fleet visibility through web and mobile platforms. "
            "Intended to help supervise vehicle movements and distributed fleets. "
            "Establish the prospect's current system and specific unmet need first."
        ),
        "rules": {"intended_use": "Vehicle location, journey visibility and fleet supervision"},
    },
    {
        "kind": "PRODUCT",
        "code": "MDVR",
        "name": "Live Vehicle and Cargo Monitoring",
        "description": (
            "Depending on configuration, supports live streaming, playback, "
            "intercom and additional cameras for side, rear or cargo visibility. "
            "Intended to investigate cargo-security concerns, delivery disputes "
            "and events during transit. Verify configuration and specific need."
        ),
        "rules": {"intended_use": "Vehicle, cargo and transit-event visibility; configuration-specific"},
    },
    {
        "kind": "PRODUCT",
        "code": "TMS",
        "name": "Transport Management System",
        "description": (
            "Manages quotations, orders, trip assignments, driver and operator apps, "
            "electronic proof of delivery, invoicing, dashboards and master data. "
            "Intended to connect transport workflows where the prospect reports "
            "disconnected processes, manual dispatching, missing delivery documents "
            "or delayed billing. Verify their current processes and unmet needs."
        ),
        "rules": {"intended_use": "Transport planning and operational workflow management; confirm specific need"},
    },
    {
        "kind": "PRODUCT",
        "code": "CONSOLIDATION_MULTI_DROP",
        "name": "Consolidation and Multi-Drop Delivery Management",
        "description": (
            "Collection-to-warehouse workflows, consolidation planning, regional "
            "delivery assignment, multi-drop jobs and end-to-end booking traceability. "
            "Intended to address shipment-tracking gaps across collection, warehouse "
            "handling and final delivery when confirmed by the prospect."
        ),
        "rules": {"intended_use": "Consolidation planning and multi-drop delivery traceability"},
    },
    {
        "kind": "PRODUCT",
        "code": "FLEET_DRIVER_ADMIN",
        "name": "Fleet and Driver Administration",
        "description": (
            "According to project scope, supports vehicle checklists, attendance, "
            "incident records, maintenance tracking, permit and inspection records, "
            "driver incentives and trip expenses. Intended to organize fleet records; "
            "confirm the specific modules required."
        ),
        "rules": {"intended_use": "Fleet and driver administration; modules depend on scope"},
    },
    {
        "kind": "PRODUCT",
        "code": "PLANT_WEIGHBRIDGE",
        "name": "Plant and Weighbridge Logistics Digitalisation (Custom)",
        "description": (
            "Custom workflows may cover orders, truck arrival, queues, loading, "
            "weighing, dockets, delivery status and customer notifications. Custom "
            "implementation subject to requirements and project scope; not confirmed "
            "as a standard deployment-ready product."
        ),
        "rules": {"intended_use": "Custom plant and weighbridge workflow; scope must be confirmed", "custom_scope": True},
    },
    {
        "kind": "PRODUCT",
        "code": "WASTE_TRANSPORT_WORKFLOW",
        "name": "Waste Collection and Transport Workflows (Custom)",
        "description": (
            "Custom systems may include customer portals, orders, credit-check "
            "workflows, manifests, fleet records, driver incentives, expenses and "
            "dashboards. Custom implementation subject to requirements and project "
            "scope; not confirmed as a standard deployment-ready product."
        ),
        "rules": {"intended_use": "Custom waste-collection and transport workflow; scope must be confirmed", "custom_scope": True},
    },
    {
        "kind": "PRODUCT",
        "code": "CUSTOM_LOGISTICS_AUTOMATION",
        "name": "Custom Logistics Workflow Automation and Integration",
        "description": (
            "Custom implementations may include customer portals, operational "
            "dashboards, automated notifications and interfaces with existing "
            "systems, subject to requirements. Not confirmed as a standard "
            "deployment-ready product; confirm requirements and scope."
        ),
        "rules": {"intended_use": "Custom logistics automation and integration; scope must be confirmed", "custom_scope": True},
    },
    {
        "kind": "ICP",
        "code": "LOGISTICS_HAULAGE",
        "name": "Transport and Haulage Operators",
        "description": (
            "Malaysian trucking and haulage companies operating trucks, prime movers, "
            "trailers or delivery fleets. Relevant needs include driver safety, "
            "incident evidence, fleet visibility and dispatching."
        ),
        "rules": {"roles": ["Owner", "Managing Director", "Operations Manager", "Fleet Manager", "Safety Manager"]},
    },
    {
        "kind": "ICP",
        "code": "THIRD_PARTY_LOGISTICS",
        "name": "Third-Party Logistics Providers",
        "description": (
            "Malaysian logistics providers coordinating transport, warehousing, "
            "subcontractors, consolidation and multiple customers. Relevant needs "
            "include shipment traceability, delivery updates, e-POD and billing accuracy."
        ),
        "rules": {"roles": ["Managing Director", "COO", "Head of Transport", "Logistics Manager", "IT Manager"]},
    },
    {
        "kind": "ICP",
        "code": "GOODS_DISTRIBUTION",
        "name": "Manufacturers, Distributors and Retailers",
        "description": (
            "Malaysian businesses moving goods through owned vehicles, contracted "
            "transporters or mixed fleets. Relevant needs include delivery visibility, "
            "transporter accountability and delivery evidence."
        ),
        "rules": {"roles": ["Supply Chain Director", "Logistics Manager", "Distribution Manager", "Operations Director"]},
    },
    {
        "kind": "ICP",
        "code": "PLANT_MATERIALS_LOGISTICS",
        "name": "Premix, Quarry and Construction Materials",
        "description": (
            "Malaysian plants managing frequent truck movements, weighing, loading "
            "and site deliveries. Potential workflow needs include truck queues, "
            "order changes, weighbridge coordination and delivery visibility."
        ),
        "rules": {"roles": ["Owner", "General Manager", "Plant Manager", "Planning Manager", "Logistics Manager"]},
    },
    {
        "kind": "ICP",
        "code": "WASTE_TRANSPORT",
        "name": "Waste Collection and Environmental Services",
        "description": (
            "Malaysian operators managing recurring customer collections, transport "
            "fleets and manifests. Potential workflow needs include collection "
            "scheduling, fleet availability, traceability and customer reporting."
        ),
        "rules": {"roles": ["Managing Director", "Operations Manager", "Fleet Manager", "Compliance Manager", "Finance Manager"]},
    },
    {
        "kind": "ICP",
        "code": "PASSENGER_TRANSPORT",
        "name": "Bus and Passenger Transport Operators",
        "description": (
            "Malaysian public, charter, school, employee or tourist bus operators. "
            "Relevant needs include driver fatigue monitoring, passenger safety, "
            "incident investigation and fleet supervision."
        ),
        "rules": {"roles": ["Owner", "Operations Director", "Fleet Manager", "Safety Manager"]},
    },
    {
        "kind": "ICP",
        "code": "HIGH_VALUE_CARGO",
        "name": "High-Value or Sensitive Cargo Transporters",
        "description": (
            "Malaysian fleets carrying electronics, valuable goods or cargo requiring "
            "close supervision. Relevant needs include cargo visibility, secure "
            "handover evidence and customer assurance."
        ),
        "rules": {"roles": ["Managing Director", "Transport Manager", "Security Manager", "Logistics Manager"]},
    },
)


def restore_catalog(db, workspace):
    added = kept = 0
    for values in ITEMS:
        existing = db.scalar(
            select(Catalog).where(
                Catalog.workspace_id == workspace.id,
                Catalog.product_line_id == default_id(db, workspace.id),
                Catalog.kind == values["kind"],
                Catalog.code == values["code"],
            )
        )
        if existing:
            kept += 1
        else:
            db.add(Catalog(workspace_id=workspace.id, **values))
            added += 1
    db.commit()
    return added, kept


def main():
    parser = argparse.ArgumentParser(
        description="Add missing documented LorrySystem offerings and proposed ICP segments."
    )
    parser.add_argument("--workspace", default="LorrySystem")
    parser.add_argument(
        "--confirm-workspace",
        required=True,
        help="Repeat the exact workspace name as a safeguard before writing catalog records.",
    )
    args = parser.parse_args()
    if args.confirm_workspace != args.workspace:
        raise SystemExit("Workspace confirmation did not match; nothing was changed.")

    with Session() as db:
        workspaces = list(
            db.scalars(select(Workspace).where(Workspace.name == args.workspace))
        )
        if len(workspaces) != 1:
            raise SystemExit(
                f"Expected exactly one workspace named {args.workspace!r}; found {len(workspaces)}."
            )
        added, kept = restore_catalog(db, workspaces[0])
        print(
            f"Catalog restore complete for {workspaces[0].name}: "
            f"{added} added, {kept} already present. Existing entries were not overwritten."
        )


if __name__ == "__main__":
    main()
