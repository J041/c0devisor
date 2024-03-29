import os
import re
import laravel

ERR_MESSAGE = {"error": "Framework defined incorrectly, or an error has occurred"}
SUPPORTED_FRAMEWORKS = {"Illuminate": "Route::", "FastRoute": ""}

route_definer = ""
framework = ""


def default_choice():
    """Default option, usually something went wrong"""
    print("Something went wrong")


def find_routes(framework, line, parameter=None):
    """Filters which function to use based on what framework was chosen"""

    framework_functions = {
        "Illuminate": laravel.get_blocks,
    }
    # Invokes the value corresponding to the key in the dictionary
    handler = framework_functions.get(framework, default_choice)

    # Checks for parameter before executing
    try:
        if parameter is not None:
            routes = handler(parameter)
            if not None and (len(routes) > 1):
                return routes
            return None
        else:
            return handler()
    except Exception as e:
        1==1


def get_routes(file_path, framework_found, userinput=""):
    """Searches for usage of frameworks in a single file"""
    global route_definer, framework
    opcode_d = file_path.replace(".php", ".txt")

    # Regex for finding the defined framework
    framework_identifier = r"use\s+([a-zA-Z0-9]+).*"

    # Compile the regex pattern
    c_framework_identifier = re.compile(framework_identifier, re.IGNORECASE)
    if framework_found == 1:
        with open(file_path, "r", errors="replace") as f:
            for line in f:
                if route_definer in line:
                    routes = find_routes(framework, line, opcode_d)
                    return routes, framework_found
    else:
        if userinput != "":
            if userinput in SUPPORTED_FRAMEWORKS:
                framework_found = 1
                framework = userinput
                route_definer = SUPPORTED_FRAMEWORKS[userinput]
                with open(file_path, "r", errors="replace") as f:
                    for line in f:
                        if route_definer in line:
                            routes = find_routes(userinput, line, opcode_d)
                            return routes, framework_found
        else:
            with open(file_path, "r", errors="replace") as f:
                for line in f:
                    match = re.search(c_framework_identifier, line)
                    if match:
                        if match.group(1) in SUPPORTED_FRAMEWORKS:
                            framework_found = 1
                            framework = match.group(1)
                            route_definer = SUPPORTED_FRAMEWORKS[framework]
                            if route_definer in line:
                                routes = find_routes(match, line, opcode_d)
                                return routes, framework_found
    return None, framework_found
