# -*- coding: utf-8 -*-
# Copyright (c) 2015, Aakvatech Limited and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
import time
import datetime
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc
import json
from frappe.utils import nowdate, cstr, cint, flt, comma_or, now
from frappe import _, msgprint
from trans_ms.utlis.dimension import set_dimension


class VehicleTrip(Document):
    # def before_insert(self):
    #     self.set_expenses()
    #     self.set_driver()

    def on_submit(self):
        if not self.stock_out_entry:
            frappe.throw(_("Stock Out Entry is not set"))

    def onload(self):
        # Load approved fuel for main trip
        # if self.transporter_type not in ["Sub-Contractor", "Self Drive"] and self.get(
        #     "main_route"
        # ):
        #     consumption = frappe.db.get_value(
        #         "Vehicle", self.get("vehicle"), "fuel_consumption"
        #     )
        #     route = frappe.db.get_value(
        #         "Trip Route", self.get("main_route"), "total_distance"
        #     )
        #     approved_fuel = consumption * route
        #     self.set("main_approved_fuel", str(approved_fuel) + " Litres")

        # Load approved fuel for return trip
        if self.transporter_type not in ["Sub-Contractor", "Self Drive"] and self.get(
            "return_route"
        ):
            consumption = frappe.db.get_value(
                "Vehicle", self.get("vehicle"), "fuel_consumption"
            )
            route = frappe.db.get_value(
                "Trip Route", self.get("return_route"), "total_distance"
            )
            approved_fuel = consumption * route
            self.set("return_approved_fuel", str(approved_fuel) + " Litres")

        # self.load_customer_contacts()

        if not self.company:
            self.company = frappe.defaults.get_user_default(
                "Company"
            ) or frappe.defaults.get_global_default("company")

    def before_insert(self):
        self.set_expenses()

    def validate(self):
        self.validate_fuel_requests()
        self.set_driver()

    def set_expenses(self):
        reference_doc = frappe.get_doc(self.reference_doctype, self.reference_docname)
        self.main_route = reference_doc.route
        reference_route = frappe.get_doc("Trip Route", self.main_route)
        if len(reference_route.fixed_expenses) > 0:
            self.main_requested_funds = []
            for row in reference_route.fixed_expenses:
                fixed_expense_doc = frappe.get_doc("Fixed Expense", row.expense)
                aday = nowdate()
                new_row = self.append("main_requested_funds", {})
                new_row.request_date = aday
                new_row.request_amount = row.amount
                new_row.request_currency = row.currency
                new_row.request_status = "Pre-Approved"
                new_row.expense_type = row.expense
                new_row.expense_account = fixed_expense_doc.expense_account
                new_row.payable_account = fixed_expense_doc.cash_bank_account

    def set_driver(self):
        if not self.driver:
            frappe.throw("Driver is not set")
        employee = frappe.db.get_value("Driver", self.driver, "employee")

        # ./frappe.msgprint(employee)
        for row in self.main_requested_funds:
            row.party_type = "Employee"
            row.party = employee

    def before_save(self):
        # validate_requested_funds(self)
        self.validate_main_route_inputs()
        # self.validate_return_route_inputs()

    def validate_fuel_requests(self):
        make_request = False

        # Check main trip
        for request in self.get("main_fuel_request"):
            if request.status == "Open":
                make_request = True

        # # Check return trip
        # for request in self.get("return_fuel_request"):
        #     if request.status == "Open":
        #         make_request = True

        if make_request:
            existing_fuel_request = frappe.db.get_value(
                "Fuel Request",
                {"reference_doctype": "Vehicle Trip", "reference_docname": self.name},
            )

            # Timestamp
            ts = time.time()
            timestamp = datetime.datetime.fromtimestamp(ts).strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            if existing_fuel_request:
                doc = frappe.get_doc("Fuel Request", existing_fuel_request)
                doc.db_set("modified", timestamp)
                if "Fully Processed" == doc.status:
                    doc.db_set("status", "Partially Processed")
            else:
                fuel_request = frappe.new_doc("Fuel Request")
                fuel_request.update(
                    {
                        "vehicle_plate_number": self.get("vehicle_plate_number"),
                        "reference_doctype": "Vehicle Trip",
                        "reference_docname": self.name,
                        "status": "Waiting Approval",
                    }
                )
                fuel_request.insert(ignore_permissions=True)

            # Mark the requests as open
            for request in self.get("main_fuel_request"):
                if request.status == "Open":
                    request.set("status", "Requested")

            # for request in self.get("return_fuel_request"):
            #     if request.status == "Open":
            #         request.set("status", "Requested")

    def validate_main_route_inputs(self):
        loading_date = None
        offloading_date = None

        steps = self.get("main_route_steps")
        for step in steps:
            if step.location_type == "Loading Point":
                loading_date = step.loading_date
            if step.location_type == "Offloading Point":
                offloading_date = step.offloading_date
        if offloading_date and not loading_date:
            frappe.throw("Loading Date must be set before Offloading Date")

    # def validate_return_route_inputs(self):
    #     # Check return trip
    #     loading_date = None
    #     offloading_date = None

    #     steps = self.get("return_route_steps")
    #     for step in steps:
    #         if step.location_type == "Loading Point":
    #             loading_date = step.loading_date
    #         if step.location_type == "Offloading Point":
    #             offloading_date = step.offloading_date
    #     if offloading_date and not loading_date:
    #         frappe.throw("Loading Date must be set before Offloading Date")

    # def load_customer_contacts(self):
    #     """Loads address list and contact list in `__onload`"""
    #     from frappe.contacts.doctype.address.address import get_address_display

    #     if self.main_customer:
    #         filters = [
    #             ["Dynamic Link", "link_doctype", "=", "Customer"],
    #             ["Dynamic Link", "link_name", "=", self.main_customer],
    #             ["Dynamic Link", "parenttype", "=", "Address"],
    #         ]
    #         address_list = frappe.get_all("Address", filters=filters, fields=["*"])

    #         address_list = [
    #             a.update({"display": get_address_display(a)}) for a in address_list
    #         ]

    #         address_list = sorted(
    #             address_list,
    #             lambda a, b: (int(a.is_primary_address - b.is_primary_address))
    #             or (1 if a.modified - b.modified else 0),
    #             reverse=True,
    #         )

    #         self.set_onload("main_addr_list", {"addr_list": address_list})

    #     if self.main_consignee:
    #         filters = [
    #             ["Dynamic Link", "link_doctype", "=", "Customer"],
    #             ["Dynamic Link", "link_name", "=", self.main_consignee],
    #             ["Dynamic Link", "parenttype", "=", "Address"],
    #         ]
    #         address_list = frappe.get_all("Address", filters=filters, fields=["*"])

    #         address_list = [
    #             a.update({"display": get_address_display(a)}) for a in address_list
    #         ]

    #         address_list = sorted(
    #             address_list,
    #             lambda a, b: (int(a.is_primary_address - b.is_primary_address))
    #             or (1 if a.modified - b.modified else 0),
    #             reverse=True,
    #         )

    #         self.set_onload("main_consignee_addr_list", {"addr_list": address_list})

    #     if self.main_shipper:
    #         filters = [
    #             ["Dynamic Link", "link_doctype", "=", "Customer"],
    #             ["Dynamic Link", "link_name", "=", self.main_shipper],
    #             ["Dynamic Link", "parenttype", "=", "Address"],
    #         ]
    #         address_list = frappe.get_all("Address", filters=filters, fields=["*"])

    #         address_list = [
    #             a.update({"display": get_address_display(a)}) for a in address_list
    #         ]

    #         address_list = sorted(
    #             address_list,
    #             lambda a, b: (int(a.is_primary_address - b.is_primary_address))
    #             or (1 if a.modified - b.modified else 0),
    #             reverse=True,
    #         )

    #         self.set_onload("main_shipper_addr_list", {"addr_list": address_list})

    # if self.return_customer:
    #     filters = [
    #         ["Dynamic Link", "link_doctype", "=", "Customer"],
    #         ["Dynamic Link", "link_name", "=", self.return_customer],
    #         ["Dynamic Link", "parenttype", "=", "Address"],
    #     ]
    #     address_list = frappe.get_all("Address", filters=filters, fields=["*"])

    #     address_list = [
    #         a.update({"display": get_address_display(a)}) for a in address_list
    #     ]

    #     address_list = sorted(
    #         address_list,
    #         lambda a, b: (int(a.is_primary_address - b.is_primary_address))
    #         or (1 if a.modified - b.modified else 0),
    #         reverse=True,
    #     )

    #     self.set_onload("return_addr_list", {"addr_list": address_list})

    # if self.return_consignee:
    #     filters = [
    #         ["Dynamic Link", "link_doctype", "=", "Customer"],
    #         ["Dynamic Link", "link_name", "=", self.main_consignee],
    #         ["Dynamic Link", "parenttype", "=", "Address"],
    #     ]
    #     address_list = frappe.get_all("Address", filters=filters, fields=["*"])

    #     address_list = [
    #         a.update({"display": get_address_display(a)}) for a in address_list
    #     ]

    #     address_list = sorted(
    #         address_list,
    #         lambda a, b: (int(a.is_primary_address - b.is_primary_address))
    #         or (1 if a.modified - b.modified else 0),
    #         reverse=True,
    #     )

    #     self.set_onload("return_consignee_addr_list", {"addr_list": address_list})

    # if self.return_shipper:
    #     filters = [
    #         ["Dynamic Link", "link_doctype", "=", "Customer"],
    #         ["Dynamic Link", "link_name", "=", self.main_shipper],
    #         ["Dynamic Link", "parenttype", "=", "Address"],
    #     ]
    #     address_list = frappe.get_all("Address", filters=filters, fields=["*"])

    #     address_list = [
    #         a.update({"display": get_address_display(a)}) for a in address_list
    #     ]

    #     address_list = sorted(
    #         address_list,
    #         lambda a, b: (int(a.is_primary_address - b.is_primary_address))
    #         or (1 if a.modified - b.modified else 0),
    #         reverse=True,
    #     )

    #     self.set_onload("return_shipper_addr_list", {"addr_list": address_list})


@frappe.whitelist(allow_guest=True)
def create_vehicle_trip(**args):

    args = frappe._dict(args)
    existing_vehicle_trip = frappe.db.get_value(
        "Vehicle Trip",
        {
            "reference_doctype": args.reference_doctype,
            "reference_docname": args.reference_docname,
        },
    )

    # existing_return_trip = frappe.db.get_value(
    #     "Vehicle Trip",
    #     {
    #         "return_reference_doctype": args.reference_doctype,
    #         "return_reference_docname": args.reference_docname,
    #     },
    # )

    if existing_vehicle_trip:
        # Mark the request as open and update modified time
        trip = frappe.get_doc("Vehicle Trip", existing_vehicle_trip)
        # doc.db_set("request_status", "open")
        # doc.db_set("modified", timestamp)
        return trip
    # elif existing_return_trip:
    #     trip = frappe.get_doc("Vehicle Trip", existing_vehicle_trip)
    #     return trip
    else:
        cargo_details = frappe.get_doc("Cargo Details", args.cargo)
        trip = frappe.new_doc("Vehicle Trip")
        trip.update(
            {
                "reference_doctype": args.reference_doctype,
                "reference_docname": args.reference_docname,
                "status": "En Route",
                "hidden_status": 2,
                "main_cargo_location_country": cargo_details.cargo_location_country,
                "main_cargo_location_city": cargo_details.cargo_location_city,
                "main_cargo_destination_country": cargo_details.cargo_destination_country,
                "main_cargo_destination_city": cargo_details.cargo_destination_city,
                "driver": args.driver,
            }
        )
        trip.insert(ignore_permissions=True, ignore_mandatory=True)

        # Update transport assignment
        doc = frappe.get_doc(args.reference_doctype, args.reference_docname)
        doc.created_trip = trip.name
        doc.status = "Processed"
        doc.save()

        # If company vehicle, update vehicle status
        if args.transporter == "In House":
            vehicle = frappe.get_doc("Vehicle", args.vehicle)
            vehicle.status = "In Trip"
            # vehicle.hidden_status = 2
            vehicle.current_trip = trip.name
            vehicle.save()
        return trip


# @frappe.whitelist(allow_guest=True)
# def create_return_trip(**args):
#     args = frappe._dict(args)

#     existing_vehicle_trip = frappe.db.get_value(
#         "Vehicle Trip",
#         {
#             "reference_doctype": args.reference_doctype,
#             "reference_docname": args.reference_docname,
#         },
#     )

#     existing_return_trip = frappe.db.get_value(
#         "Vehicle Trip",
#         {
#             "return_reference_doctype": args.reference_doctype,
#             "return_reference_docname": args.reference_docname,
#         },
#     )

#     if existing_vehicle_trip:
#         # Mark the request as open and update modified time
#         trip = frappe.get_doc("Vehicle Trip", existing_vehicle_trip)
#         # doc.db_set("request_status", "open")
#         # doc.db_set("modified", timestamp)
#         return trip
#     elif existing_return_trip:
#         trip = frappe.get_doc("Vehicle Trip", existing_return_trip)
#         return trip
#     else:
#         # If internal tranport
#         if args.transporter == "In House":
#             vehicle = frappe.get_doc("Vehicle", args.vehicle)
#             vehicle.status = "En Route - Returning"
#             vehicle.hidden_status = 4

#         doc = frappe.get_doc("Vehicle Trip", args.vehicle_trip)
#         doc.return_reference_doctype = args.reference_doctype
#         doc.return_reference_docname = args.reference_docname
#         doc.status = "En Route - Returning"
#         doc.hidden_status = 4
#         doc.save()
#         # for vehicle
#         vehicle.current_trip = doc.name
#         vehicle.save()
#         return doc


@frappe.whitelist()
def make_vehicle_inspection(source_name, target_doc=None, ignore_permissions=False):

    docs = get_mapped_doc(
        "Vehicle Trip",
        source_name,
        {
            "Vehicle Trip": {
                "doctype": "Vehicle Inspection",
                "field_map": {
                    "driver_name": "driver_name",
                    "vehicle_plate_number": "vehicle_plate_number",
                    "name": "trip_reference",
                },
                "validation": {
                    "docstatus": ["=", 0],
                },
            }
        },
        target_doc,
        postprocess=None,
        ignore_permissions=ignore_permissions,
    )

    return docs


@frappe.whitelist(allow_guest=True)
def check_trip_status(**args):
    args = frappe._dict(args)
    frappe.msgprint("ok")

    # get trip
    # existing_trip = frappe.db.get_value("Vehicle Trip",
    # {"main_file_number": args.file_number})
    # frappe.msgprint("got")

    # get trip
    existing_trip = frappe.db.get_value(
        "Vehicle Trip", {"main_file_number": args.file_number}
    )
    if existing_trip:
        doc = frappe.get_doc("Vehicle Trip", existing_trip)
        status = doc.status
        frappe.msgprint(status)
        if status != "Closed":
            frappe.msgprint(
                "Cannot Close the File because it's Trip is not closed,Please Create the Trip"
            )
        else:
            return status
    else:
        frappe.msgprint(
            "Cannot Close because Trip has not been created yet for the current file"
        )


"""@frappe.whitelist(allow_guest=True)
def validate_route_inputs(**args):
	args = frappe._dict(args)

	frappe.msgprint("OOOOOKKKK")

	#trip = frappe.db.get_value("Vehicle Trip", {"name": args.name})
	#docs = frappe.get_doc("Vehicle Trip", trip)
	#steps=docs.main_route_steps

	if args.offloading_date and not args.loading_date:
		frappe.msgprint("Loading Steps must be filled before offloading",raise_exeption==True)
"""


# def validate_requested_funds(doc):
# 	make_request = False
# 	open_requests = []
# 	for requested_fund in doc.requested_funds:
# 		if requested_fund.request_status == "open":
# 			make_request = True
# 			open_requests.append(requested_fund)


@frappe.whitelist()
def create_fund_jl(doc, row):
    doc = frappe.get_doc(json.loads(doc))
    row = frappe._dict(json.loads(row))
    if row.journal_entry:
        frappe.throw("Journal Entry Already Created")

    accounts = []
    debit_row = dict(
        account=row.expense_account,
        debit_in_account_currency=row.request_amount,
        cost_center=row.cost_center,
        # department=row.get("department") or doc.get("department"),
    )
    accounts.append(debit_row)
    credit_row = dict(
        account=row.payable_account,
        credit_in_account_currency=row.request_amount,
        cost_center=row.cost_center,
        party_type=row.party_type,
        party=row.party,
        # department=row.get("department") or doc.get("department"),
    )
    accounts.append(credit_row)

    company = doc.company
    user_remark = "Vehicle Trip No: {0}".format(doc.name)
    date = nowdate()
    jv_doc = frappe.get_doc(
        dict(
            doctype="Journal Entry",
            posting_date=date,
            accounts=accounts,
            cheque_date=date,
            company=company,
            user_remark=user_remark,
            # department=row.get("department") or doc.get("department"),
        )
    )
    jv_doc.flags.ignore_permissions = True
    frappe.flags.ignore_account_permission = True
    set_dimension(doc, jv_doc)
    for row in jv_doc.accounts:
        set_dimension(doc, jv_doc, tr_child=row)
    jv_doc.save()
    # jv_doc.submit()
    jv_url = frappe.utils.get_url_to_form(jv_doc.doctype, jv_doc.name)
    si_msgprint = "Journal Entry Created <a href='{0}'>{1}</a>".format(
        jv_url, jv_doc.name
    )
    frappe.msgprint(_(si_msgprint))
    for item in doc.requested_funds:
        if item.name == row.name:
            item.journal_entry = jv_doc.name
    doc.save()
    return jv_doc


@frappe.whitelist()
def create_stock_out_entry(doc, fuel_stock_out):
    doc = frappe.get_doc(json.loads(doc))
    if doc.stock_out_entry:
        return frappe.get_doc("Stock Entry", doc.stock_out_entry)
    fuel_item = frappe.get_value("Transport Settings", None, "fuel_item")
    if not fuel_item:
        frappe.throw(_("Please Set Fuel Item in Transport Settings"))
    warehouse = frappe.get_value("Vehicle", doc.vehicle, "fuel_warehouse")
    if not warehouse:
        frappe.throw(_("Please Set Fuel Warehouse in Vehicle"))
    item = {"item_code": fuel_item, "qty": float(fuel_stock_out)}
    stock_entry_doc = frappe.get_doc(
        dict(
            doctype="Stock Entry",
            from_bom=0,
            posting_date=nowdate(),
            posting_time=now(),
            items=[item],
            stock_entry_type="Material Issue",
            purpose="Material Issue",
            from_warehouse=warehouse,
            # to_warehouse=dispatch_bay_wh,
            company=doc.company,
            remarks="Transfer for {0} in vehicle {1}".format(
                doc.driver_name,
                doc.vehicle,
            ),
        )
    )
    set_dimension(doc, stock_entry_doc)
    set_dimension(doc, stock_entry_doc, tr_child=stock_entry_doc.items[0])
    stock_entry_doc.insert(ignore_permissions=True)
    doc.stock_out_entry = stock_entry_doc.name
    doc.save()
    return stock_entry_doc
