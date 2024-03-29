import json
from urllib.parse import unquote
import re


# define methods to be detected.
METHODS = ["'get'", "'any'", "'post'", "'delete'", "'put'"]


def get_blocks(filename):

    # ^ Grab contents of vld
    with open(filename, "r") as f:
        contents_splitlines = f.read().splitlines()

    # ^ Initializing variables
    stack = []
    start_end = []

    # ^ Checking through each line to identify different blocks of VLD that indicates different dynamic functions
    for i in range(len(contents_splitlines)):

        # ^ Matching start of defined dynamic function
        start_match = re.fullmatch(r"Dynamic Function (\d+)", contents_splitlines[i])

        if start_match:
            # ^ Cuz i start from 0
            start_number = i + 1

            # ^ Capture Group is function number
            function_number = start_match.group(1)

            # ^ Used for identifying how many lines each dynamic function spans
            stack.append((function_number, start_number))

        elif re.fullmatch(r"End of Dynamic Function (\d+)", contents_splitlines[i]):
            if stack:
                function_number, start_number = stack.pop()
                end_number = i + 1
                start_end.append((start_number, end_number))
            else:
                print(f"An Error Occurred, a value was not properly processed: {stack}")

    start_end.append((0, len(contents_splitlines)))
    sorted_start_end = sorted(start_end, key=lambda x: x[0])
    routes = find_child_routes(sorted_start_end, contents_splitlines, filename)
    if not None and (len(routes) > 0):
        return routes
    else:
        return None


def get_prefix(line, filename):
    prefix_regex = re.compile(r"\s*\'prefix\'\s*=>\s*\'([a-zA-Z0-9\-\_]*)\'")
    middleware_regex = re.compile(r"\s*\'middleware\'\s*=>\s*\'([a-zA-Z0-9\-\_]*)\'")
    line_num_PHP = int(line.split()[0])

    with open(filename.replace("txt", "php"), "r", errors="replace") as file:
        php_line = file.read().splitlines()[line_num_PHP - 1]
        match_prefix = re.search(prefix_regex, php_line)
        match_middleware = re.search(middleware_regex, php_line)
        if match_prefix:
            return match_prefix.group(1)
        else:
            if match_middleware:
                return match_middleware.group(1)
        return None


def find_child_routes(sorted_start_end, contents_splitlines, filename, _prefix=""):
    child_list = [sorted_start_end[0]]
    urls = []
    null_end_number = sorted_start_end[0][1]

    for i in range(1, len(sorted_start_end)):
        if null_end_number > sorted_start_end[i][1]:
            child_list.append(sorted_start_end[i])

    for i in range(len(child_list)):
        values = child_list[i]
        dyna = contents_splitlines[values[0] : values[1]]

        for lines in dyna:
            check_lines = lines.split()

            if "RETURN" in lines:
                return urls

            if check_lines == [] or not check_lines[0].isdigit():
                continue

            if "group" in lines:
                prefix = get_prefix(lines, filename)
                if (_prefix != None) and (_prefix):
                    prefix = _prefix + "/" + prefix
                sub_urls = find_child_routes(
                    child_list[1:], contents_splitlines, filename, prefix
                )
                for sub_url in sub_urls:
                    urls.append(sub_url)
                child_list.pop(i + 1)
            elif ("INIT_STATIC_METHOD_CALL" in lines) and (check_lines[-1] in METHODS):
                line_number = int(lines.split()[0])

                with open(filename.replace("txt", "php"), "r", errors="replace") as f:
                    PHP_line = f.read().splitlines()[line_number - 1]
                    match = re.search(
                        r"Route::([a-zA-Z]+)\s*\('([\S]+)', ([\s\S]+?)\)", PHP_line
                    )
                    if match:
                        method = match.group(1)
                        route = match.group(2)
                        if _prefix:
                            full_route = f"{method}:{_prefix}{route}"
                        else:
                            full_route = f"{method}:{route}"
                        urls.append(full_route)

    return urls
