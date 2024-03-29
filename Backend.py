from zipfile import ZipFile
from urllib.parse import unquote
from helper import (
    get_self_filename,
    file_func_map_to_directory_structure,
    get_variable_trace_query,
    dataframe_to_dictionary,
)
from graphviz.backend.execute import CalledProcessError
import os, json, re, lxml.etree, copy, threading, queue, functools
import routes as route
from app import UPLOAD_FOLDER, V_LIBRARY, GRAPH_LIBRARY, graph_ext
from multiprocessing import Process, Queue

# ^ Globals
# $ Pink
# ! RED
# * GREEN
# ? BLUE
id = 0
web_apps = []
mutex = threading.Lock()
id_mutex = threading.Lock()

#! ========================================================================== #
#!                               Decorators
#! ========================================================================== #


def timeout(seconds=600, default=None):

    def decorator(func):
        def handler(queue, func, args, kwargs):
            queue.put(func(*args, **kwargs))

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            q = Queue()
            p = Process(target=handler, args=(q, func, args, kwargs))
            p.start()
            p.join(timeout=seconds)

            if p.is_alive():
                # process still alive when timeout
                p.terminate()
                p.join()
                if hasattr(default, "__call__"):
                    return default()
                else:
                    raise TimeoutError("Process took too long")
            else:
                return q.get()

        return wrapper

    return decorator


def resubmit_file(file, upload_folder=UPLOAD_FOLDER):
    dst_folder = extract_files(file)

    if dst_folder == -1:
        return dst_folder

    new_folder = os.path.split(dst_folder)[-1]
    folder_path = os.path.join(upload_folder, new_folder)
    render_result = view_graph(new_folder, -1, folder_path, True)
    if type(render_result) is str:
        print("Error: ", render_result)
        return -1

    return dst_folder


def gen_route(folder_name, framework, vld_file):
    JSON_route = route.get_routes(folder_name, framework, vld_file)
    return JSON_route


def get_php_files(handle):
    """Returns list of php files from recursively searching folder provided"""
    list_of_php_files = []
    for root, subdirs, files in os.walk(handle):
        for File in files:
            # Checking if file extension is php
            extn = File.split(sep=".")[-1]
            if extn == "php":
                # Creating a list of PHP files to extract data from
                list_of_php_files.append(os.path.join(root, File.replace("\\", "/")))
    return list_of_php_files


def generate_vld(file_name):
    """Accepts a single php file and runs vld without execution on it."""
    vld_output = file_name.replace(".php", ".txt")
    os.system(
        f"php -d vld.active=1 -d vld.execute=0 '{file_name}' > '{vld_output}' 2>&1"
    )
    # TODO: Error handling of non-php files
    # TODO: Handle invalid php files
    return vld_output


def generate_data(php_handle, vld_handle):
    """Extracts data from provided php and vld txt file
    Writes data to json file
    """

    #! ===============================================================
    #! Definitions
    #! ===============================================================
    # * Persist function id across php files

    # * Generates page_url for (null) functions

    page_url = get_self_filename(php_handle, True)

    # * Define JSON Object structure
    J_data = {
        "function": [],
        "page": {
            "url": page_url,
            "source": [],
            "destination": [],
        },
    }

    php_code_blocks = []
    html_code_blocks = []

    html_parser = lxml.etree.HTMLParser()

    #! ===============================================================
    #! File Operations
    #! ===============================================================

    # * Extract data from PHP file
    with open(php_handle, "r", errors="replace") as php_file:
        page_content = php_file.read()

        # * Use regular expressions to find PHP code blocks
        blocks = re.findall(
            r"([\s\S]*?)(?:(<\?php[\s\S]+?\?>)|\Z)", page_content, re.DOTALL
        )
        php_code_blocks.extend(capture[1] for capture in blocks)

        # * Use regular expressions to find HTML code blocks
        html_code_blocks.extend(capture[0] for capture in blocks)

        # * use iterators and stack?
        page_content = page_content.split("\n")

    # * Extract data from vld output
    with open(vld_handle, "r") as php_file:
        str_vld_output = php_file.read()

    # * Compiling regex to look for class definition in opcode dump
    class_block_regex = re.compile(
        r"Class ([a-zA-Z_\x80-\xff][a-zA-Z0-9_\x80-\xff\\]*):\n([\s\S]+?)\nEnd of class \1"
    )

    class_blocks = re.findall(class_block_regex, str_vld_output)

    # *Removes class definitions with their functions to obtain functions that don't belong to a class
    class_blocks.append((None, re.sub(class_block_regex, "", str_vld_output)))

    nnull_code_lines, null_code_lines, function_data_list = (
        [],
        [],
        [],
    )
    function_file_map = {}
    for cn, cb in class_blocks:
        capture_regex = re.compile(
            r"(?:Function ([a-zA-Z_\x80-\xff][a-zA-Z0-9_\x80-\xff]*):\n)?Finding entry points\n(?:(?:Found catch point at position: \d+\n)?Branch analysis from position: \d+\n(?:\d+ jumps found. \(Code = \d+\) (?:Position \d+ = -?\d+,? ?)+\n)?)+filename: +((?:\/[^\/\n]+)+)\nfunction name:  ([a-zA-Z_\x80-\xff][a-zA-Z0-9_\x80-\xff]*|\(null\))\nnumber of ops:  (\d+)\ncompiled vars: +((?:!\d+ = \$\w+,? *)+|none)\nline      #\* E I O op {27}fetch {10}ext  return  operands\n-+\n((?:[ \S]+\n)+)"
        )
        functions_data_raw = re.findall(capture_regex, cb)
        for f in functions_data_raw:
            code_block = []

            if f[2] == "(null)":
                continue
            else:
                yes = f[5].split("\n")
                for i in yes:
                    if len(i[0:5].strip()) > 0:
                        code_block.append(int(i[0:5].strip()))
            if len(code_block) > 0:
                for i in range(min(code_block), max(code_block) + 1):
                    null_code_lines.append(i)

    nnull_code_lines = list(set(null_code_lines))
    # ! Parsing VLD file dump
    for class_name, class_block in class_blocks:
        # ? Captures the following
        # ? 1. Function name defined in its class (lowercase, optional capture group)
        # ? 2. Filepath of php file
        # ? 3. Function name defined (case-sensitive)
        # ? 4. Number of PHP operations for that function
        # ? 5. Compiled variables (comma-separated)
        # ? 6. Detailed information of operations executed and operands used

        # * Regex for capturing main body content of vld dump
        capture_regex = re.compile(
            r"(?:Function ([a-zA-Z_\x80-\xff][a-zA-Z0-9_\x80-\xff]*):\n)?Finding entry points\n(?:(?:Found catch point at position: \d+\n)?Branch analysis from position: \d+\n(?:\d+ jumps found. \(Code = \d+\) (?:Position \d+ = -?\d+,? ?)+\n)?)+filename: +((?:\/[^\/\n]+)+)\nfunction name:  ([a-zA-Z_\x80-\xff][a-zA-Z0-9_\x80-\xff]*|\(null\))\nnumber of ops:  (\d+)\ncompiled vars: +((?:!\d+ = \$\w+,? *)+|none)\nline      #\* E I O op {27}fetch {10}ext  return  operands\n-+\n((?:[ \S]+\n)+)"
        )
        functions_data_raw = re.findall(capture_regex, class_block)

        for f in functions_data_raw:

            # * Stores the parsed vld output for the current function
            function_data = {}

            # ! Acquire mutex for shared object
            id_mutex.acquire()
            global id
            # * Increment id for identification
            id += 1

            # * Stores the data required by the application to generate function graph
            extracted_func_data = {}

            # * Assigns global variable to a local instance, to be used (Safe from Race Conditions)
            extracted_func_data["ID"] = id

            # ! Release mutex for shared object
            id_mutex.release()

            extracted_func_data["Depends"] = []
            extracted_func_data["Exports"] = []
            extracted_func_data["Class"] = "" if class_name is None else class_name
            # If function belongs to a class, prepend the class name with a . as separator
            if f[0] == f[2].lower() and class_name is not None:
                function_data["Name"] = class_name + "." + f[2]
            else:
                # If function name == (null), refers to code not belonging to a function
                # Rename to the path of the file relative to uploaded folder
                if f[2] != "(null)":
                    function_data["Name"] = f[2]

                else:
                    function_data["Name"] = page_url
                    # Extraction of required elements from HTML DOM
                    links = []
                    while len(html_code_blocks) > 0:
                        # Parse DOM into XML to use xpath for searching specific elements
                        html_tree = lxml.etree.fromstring(
                            html_code_blocks.pop(0), html_parser
                        )

                        if html_tree is None:
                            continue
                        # Get all links referenced by html
                        for element in html_tree.xpath("//a|//img|//link|//form"):
                            for key, value in element.attrib.items():
                                if key in ["href", "src", "action"]:
                                    link_info = {
                                        "element": element.tag,
                                        "text": lxml.etree.tostring(element),
                                        "Method": element.attrib.get(
                                            "method", "GET"
                                        ).upper(),
                                        "Url": value if value != "" else page_url,
                                    }
                                    if (link_info["Method"], link_info["Url"]) not in [
                                        (l["Method"], l["Url"]) for l in links
                                    ]:
                                        links.append(link_info)
                    # Sort links into dependencies and exports based on their respective element
                    for link in links:
                        if link["element"] == "img":
                            J_data["page"]["source"].append(
                                {
                                    key: link[key]
                                    for key in ("Method", "Url", "Route")
                                    if key in link
                                }
                            )
                        elif link["element"] in ["form", "a"]:
                            J_data["page"]["destination"].append(
                                {
                                    key: link[key]
                                    for key in ("Method", "Url", "Route")
                                    if key in link
                                }
                            )
                    J_data["page"]["url"] = [page_url, extracted_func_data["ID"]]

            extracted_func_data["Name"] = function_data["Name"]

            function_data["op_count"] = int(f[3])
            function_data["compiled_vars"] = f[4].split(", ")
            function_data["op"] = []
            ops = f[5].strip("\n").split("\n")

            # Track the last referenced php file line for each php operation
            php_line = 0
            # Tracks objects declared to locate methods and its corresponding class
            track_object = []

            for o in ops:
                function_data["op"].append({})

                # If line is defined, update the php line the following operations belongs to
                if o[0:5].strip().isdigit():
                    php_line = int(o[0:5])

                op_id = int(o[6:11])

                function_data["op"][op_id]["php_line"] = php_line
                function_data["op"][op_id]["unreachable"] = o[11] != "*"
                function_data["op"][op_id]["E_flag"] = o[13] == "E"
                function_data["op"][op_id]["I flag"] = o[15] == ">"
                function_data["op"][op_id]["O flag"] = o[17] == ">"
                function_data["op"][op_id]["operation"] = o[19:47].strip()
                function_data["op"][op_id]["fetch"] = o[48:62].strip()
                function_data["op"][op_id]["ext"] = (
                    int(o[65:67]) if o[65:67].isdigit() else None
                )
                function_data["op"][op_id]["return"] = o[68:74].strip(" ")
                function_data["op"][op_id]["operands"] = o[76:]

                # Variable tracking
                if len(track_object) > 0:
                    for object in track_object:
                        # copy of object["vars"] is used as it will be updated each iteration with related variables
                        for v in object["vars"].copy():
                            related_vars = []
                            for operand in function_data["op"][op_id]["operands"].split(
                                ","
                            ):
                                operand = operand.strip(" '")
                                if operand.startswith(("$", "!")):
                                    related_vars.append(operand)
                            if v in related_vars:
                                object["vars"].update(related_vars)

                if function_data["op"][op_id]["operation"] in [
                    "INIT_FCALL",
                    "INIT_FCALL_BY_NAME",
                ]:
                    extracted_func_data["Depends"].append(
                        [function_data["op"][op_id]["operands"].strip("'"), php_line]
                    )

                elif function_data["op"][op_id]["operation"] in [
                    "INIT_METHOD_CALL",
                    "INIT_STATIC_METHOD_CALL",
                ]:
                    method_operands = function_data["op"][op_id]["operands"].split(",")
                    method_name = method_operands[-1].strip("' ")
                    for operand in method_operands:
                        for object in track_object:
                            if operand in object["vars"]:
                                method_name = (
                                    object.get("class", "") + "." + method_name
                                )
                    extracted_func_data["Depends"].append([method_name, php_line])

                elif (
                    function_data["op"][op_id]["operation"] == "RETURN"
                    and function_data["op"][op_id]["O flag"]
                ):
                    extracted_func_data["Exports"].append(
                        function_data["op"][op_id]["operands"].strip('"')
                    )

                elif function_data["op"][op_id]["operation"] == "NEW":
                    new_class = function_data["op"][op_id]["operands"].strip("'")
                    track_object.append(
                        {
                            "class": new_class,
                            "vars": {function_data["op"][op_id]["return"]},
                        }
                    )

            # Get all lines from php source file that are relevant to this function
            extracted_func_data["Lines"] = {}

            c_class_def_regex = re.compile(r"class\s+[0-9a-zA-Z\_\-]+\s*.*\s*{")
            c_function_def_regex = re.compile(
                r"function\s+[\_a-zA-Z0-9\-]*\([a-zA-Z0-9\$\_\-]*\)"
            )
            c_p_function_def_regex = re.compile(
                r"public\s+function\s+[\_a-zA-Z0-9\-]*\(\)"
            )
            c_pr_function_def_regex = re.compile(
                r"private\s+function\s+[\_a-zA-Z0-9\-]*\(\)"
            )
            for i in range(function_data["op"][0]["php_line"], php_line + 1):
                php_line_content = [page_content[i - 1]]
                # Strip line to remove white spaces
                s_php_line_content = php_line_content[0].strip()
                # Remove any lines that are just newlines
                if len(s_php_line_content) != 0:
                    # If the line starts with #, the whole line thereafter will be a comment
                    if s_php_line_content[0] == "#":
                        continue
                    # If the line starts with //, the whole line thereafter will be a comment as well
                    elif s_php_line_content[0:2] == "//":
                        continue
                    for f, line in extracted_func_data["Depends"]:
                        if line == i:
                            php_line_content.append(f)

                    if len(nnull_code_lines) > 0:
                        if extracted_func_data["Name"] == page_url:

                            c_class_def_regex = re.compile(
                                r"class\s+[0-9a-zA-Z\_\-]+\s+"
                            )
                            c_function_def_regex = re.compile(
                                r"function\s+[\_a-zA-Z0-9\-]*\(\)"
                                r"function\s+[\_a-zA-Z0-9\-]*\([a-zA-Z0-9\$\_\-]*\)"
                            )
                            c_p_function_def_regex = re.compile(
                                r"public\s+function\s+[\_a-zA-Z0-9\-]*\(\)"
                            )
                            c_pr_function_def_regex = re.compile(
                                r"private\s+function\s+[\_a-zA-Z0-9\-]*\(\)"
                            )

                            match_class = re.search(
                                c_class_def_regex, s_php_line_content
                            )
                            match_function = re.search(
                                c_function_def_regex, s_php_line_content
                            )
                            match_public = re.search(
                                c_p_function_def_regex, s_php_line_content
                            )
                            match_private = re.search(
                                c_pr_function_def_regex, s_php_line_content
                            )

                            closing = int(list(nnull_code_lines)[-1]) + 1
                            if (
                                i not in nnull_code_lines
                                and not match_class
                                and not match_function
                                and not match_public
                                and not match_private
                                and i != closing
                            ):
                                extracted_func_data["Lines"][i] = [s_php_line_content]
                        else:
                            extracted_func_data["Lines"][i] = [s_php_line_content]
                    else:
                        extracted_func_data["Lines"][i] = [s_php_line_content]

            # Function to file mapping
            function_file_map[extracted_func_data["ID"]] = (
                f"{function_data['Name']}",
                f"{page_url}",
            )
            function_data_list.append(function_data)
            J_data["function"].append(extracted_func_data)

    # current line number of the vld output document
    J_data["function"] = findend(J_data)
    # TODO: check for random spacing
    json_data = json.dumps(J_data, indent=2)

    # Opens a file with a respective name and write contents of json dump
    json_handle = vld_handle.replace(".txt", ".json")
    with open(json_handle, "w") as json_dump:
        json_dump.write(json_data)
    return J_data["function"], J_data["page"], function_file_map


def findend(json_output):
    # Finds the end of conditions and loops by checking for semicolons
    # If after for or if no curly bracket, only accept 1 semicolon
    # If find a open curly bracket, find for end
    # Do FIFO method to account for nested conditions
    # Does not work if curly bracket starts more than 1 line from condition

    # open_curly_pattern = r"{(?=(?:[^\"\']*\"[^\"\']*\")*[^\"\']*$)"
    # close_curly_pattern = r"}(?=(?:[^\"\']*\"[^\"\']*\")*[^\"\']*$)"
    open_curly_pattern = r"{"
    close_curly_pattern = r"}"
    condition_pattern = r"(?i)^\s*\}?\s*((if|elseif|for|foreach|while|do|switch)|(?:else|case))(?![a-zA-Z0-9]+)\s*(?(2)\(|)"
    while_pattern = r"(?i)while\s*\(.*\)\s*\;"
    break_pattern = r"(?i)break;"
    empty_pattern = r"^\s+$"

    open_curly_compile = re.compile(open_curly_pattern)
    close_curly_compile = re.compile(close_curly_pattern)
    condition_compile = re.compile(condition_pattern)
    while_compile = re.compile(while_pattern)
    break_compile = re.compile(break_pattern)
    empty_compile = re.compile(empty_pattern)

    output_json = {}
    output_json["function"] = []

    start_line = ""

    for functions in json_output["function"]:
        final_function = {}
        temp_dict_list = []
        in_condition = 0
        condition_name = ""
        condition_counter = 0
        single_line_block = False  # Denotes that the current line has been processed due to being part of a conditional block without {}
        open_stack = []
        final_function["ID"] = functions["ID"]
        final_function["Name"] = functions["Name"]
        final_function["Depends"] = functions["Depends"]
        final_function["Exports"] = functions["Exports"]
        final_function["Class"] = functions["Class"]
        final_function["Lines"] = {}

        for line_num in functions["Lines"].keys():
            line = functions["Lines"][line_num][0]
            # Current line was handled by the previous line, skip to prevent duplicate lines
            if single_line_block:

                single_line_block = False
                continue
            if re.match(empty_compile, line) == None:

                last_line_check = False

                if (
                    re.search(close_curly_compile, line)
                    or re.search(while_compile, line)
                    or re.search(break_compile, line)
                ) and in_condition > 0:
                    if len(open_stack) > 0:

                        if re.match(condition_compile, line) == None or re.search(
                            while_compile, line
                        ):
                            (temp_dict_list[-1])[line_num] = functions["Lines"][
                                line_num
                            ]

                        last_line_check = True
                        temp = temp_dict_list.pop(-1)

                        in_condition -= 1

                        if in_condition == 0:
                            final_function["Lines"][condition_name] = copy.deepcopy(
                                temp
                            )

                        else:
                            temp_dict_list[-1][condition_name] = copy.deepcopy(temp)

                        condition_name = "-".join(condition_name.split("-")[:-1])

                if (condition_match := re.match(condition_compile, line)) and re.search(
                    while_compile, line
                ) == None:
                    condition_name = (
                        condition_name
                        + "-"
                        + re.match(condition_compile, line).group(1).strip().strip("(")
                        + "+"
                        + str(condition_counter)
                    )

                    condition_counter += 1
                    if in_condition > 0:
                        temp_dict_list[-1][condition_name] = {}
                    temp_dict_list.append({line_num: functions["Lines"][line_num]})

                    # Finds program control keywords that do not have a {} block
                    # treat such cases as a one-liner block that ends when a semicolon is reached
                    # TODO: Include nested one-liner statement in the same line as if-else/for/while declaration
                    if re.search(open_curly_compile, line) == None and re.match(
                        r".*?;\s*$", functions["Lines"].get(line_num + 1, [""])[0]
                    ):
                        single_line_block = True  # lookaheead and add the next line into the current conditional block
                        if not last_line_check:
                            (temp_dict_list[-1])[line_num] = functions["Lines"][
                                line_num
                            ]
                            (temp_dict_list[-1])[line_num + 1] = functions["Lines"][
                                line_num + 1
                            ]
                            last_line_check = False
                            # The whole conditional block has been read
                            temp = temp_dict_list.pop(-1)
                            if in_condition == 0:
                                final_function["Lines"][condition_name] = copy.deepcopy(
                                    temp
                                )
                            else:
                                temp_dict_list[-1][condition_name] = copy.deepcopy(temp)

                            condition_name = "-".join(condition_name.split("-")[:-1])
                        continue

                    in_condition += 1

                if in_condition > 0:
                    if not last_line_check:
                        (temp_dict_list[-1])[line_num] = functions["Lines"][line_num]
                        last_line_check = False

                else:
                    if not last_line_check:
                        final_function["Lines"][line_num] = functions["Lines"][line_num]
                        last_line_check = False

                if re.search(open_curly_compile, line):
                    open_stack.append(line_num)

        output_json["function"].append(final_function)
    #     json_data = json.dumps(output_json, indent=2)
    # with open("./output1.json", "w") as json_dump:
    #     json_dump.write(json_data)
    return output_json["function"]


def convert_function_name_to_id(ordered_function_names, function_data_handle):

    with open(function_data_handle, "r+") as file:
        data = json.load(file)
        for i, function in enumerate(data["function"]):
            for j, depend in enumerate(function["Depends"]):
                for id, function_name_file in ordered_function_names.items():
                    if function_name_file[0] == depend[0]:
                        data["function"][i]["Depends"][j][1] = id + 1
                        break
            for j, line in function["Lines"].items():

                def recurse_lines(line):
                    if type(line) is dict:
                        for k, v in line.items():
                            line[k] = recurse_lines(v)
                    elif len(line) > 1:
                        for f in range(1, len(line)):
                            for (
                                id,
                                function_name_file,
                            ) in ordered_function_names.items():
                                if list(function_name_file)[0] == line[f]:
                                    line[f] = id + 1  # id starts at 1
                                    break
                    return line

                data["function"][i]["Lines"][j] = recurse_lines(line)
        file.seek(0)
        file.truncate(0)

        file.write(json.dumps(data))


def process_files(
    files,
    webapp_routes,
    page_links_map,
    page_links,
    function_file_map,
    destination_folder,
    framework_found,
    result_q,
):

    for f in files:
        vld_file = generate_vld(f)
        routes, framework_found = route.get_routes(f, framework_found)
        if routes != None:
            webapp_routes["Routes"] += routes

        #! This creates individual parts, will need to append them into a list
        f_data, page_links, function_files = generate_data(f, vld_file)

        #! Mutex acquire
        mutex.acquire()

        page_links_map.append(page_links)
        function_file_map.update(function_files)

        with open(os.path.join(destination_folder, "functions.json"), "r+") as f:
            existing = json.load(f)
            f.seek(0)
            existing["function"].extend(f_data)
            existing["function"] = sorted(existing["function"], key=lambda f: f["ID"])

            f.write(json.dumps(existing))
        #! Mutex release
        mutex.release()

    webapp_routes["Routes"].extend(page_links_map)

    result_q.put(webapp_routes)
    result_q.put(page_links_map)
    result_q.put(function_file_map)


def extract_files(file_handle):

    # ^ Definitions
    page_links_map = []
    page_links = {}
    webapp_routes = {"Routes": []}
    function_file_map = {}
    framework_found = 0
    result_q = queue.Queue()
    threads = []

    destination_folder, filename = os.path.split(file_handle)
    if (
        not destination_folder
        or destination_folder == ""
        or not filename
        or filename == ""
    ):
        return -1
    # return destination_folder
    # ^ Extract zip file contents
    if filename.endswith(".zip"):
        with ZipFile(os.path.join(destination_folder, filename), "r") as zipfile:

            # ^ Create destination folder
            os.makedirs(destination_folder, exist_ok=True)

            # ^ Extract contents into destination folder
            zipfile.extractall(destination_folder)

    # ^ retrieve all PHP files
    files = get_php_files(destination_folder)

    with open(os.path.join(destination_folder, "functions.json"), "w") as f:
        f.write(json.dumps({"function": []}))

    #! ================================================================
    #!              Dividing work load into equal lengths
    #! ================================================================
    number_of_threads = 5  # TODO: Can change the number of threads here
    length = len(files)
    slice_len = length // number_of_threads
    remainder = length % number_of_threads
    start = 0
    slices = []

    for i in range(number_of_threads):
        slice_end = start + slice_len + (1 if i < remainder else 0) - 1
        slices.append(files[start : slice_end + 1])
        start = slice_end + 1

    #! ================================================================
    #!                          Creating Threads
    #! ================================================================
    for file_slices in slices:
        thread = threading.Thread(
            target=process_files,
            args=(
                file_slices,
                webapp_routes,
                page_links_map,
                page_links,
                function_file_map,
                destination_folder,
                framework_found,
                result_q,
            ),
        )
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    #! ================================================================
    #!                      Get results from Queue
    #! ================================================================
    webapp_routes = result_q.get()
    page_links_map = result_q.get()
    function_file_map = result_q.get()
    function_file_map = {
        k : function_file_map[k] 
        for k in sorted(function_file_map.keys())
        }

    with open(os.path.join(destination_folder, "627main.json"), "w") as f:
        f.write(json.dumps(webapp_routes))
    with open(os.path.join(destination_folder, "func_file.json"), "w") as f:
        f.write(json.dumps(function_file_map))
    convert_function_name_to_id(
        function_file_map, os.path.join(destination_folder, "functions.json")
    )
    return destination_folder  # consider returning list of json files


def view_graph(filename, func_id, folder_path, regenerate=False):

    # ? folder_path = Relative folder path
    # ? Append '/' at the beginning of string for html links
    # ? Has no root symbol

    # ? List of all functions data
    functions_data = []

    # ? List of all functions names to populate the function menu (Left sidebar)
    function_names = [("Routes", None)]

    # ? Route graph defaults to None, set on user request
    route_graph = None

    # ? Boolean to check if all graph is rendered
    all_rendered = False

    try:
        # ! Retrieve all function names and corresponding file as tuple
        json_file_path = os.path.join(folder_path, "func_file.json")
        with open(json_file_path, "r") as json_file:
            func_file_dict = json.load(json_file)
            function_names += [v for v in func_file_dict.values()]

        # ! Retrieve all function data
        json_file_path = os.path.join(folder_path, "functions.json")
        with open(json_file_path, "r") as json_file:
            functions_data = V_LIBRARY.get_data(json_file_path, "function")
        # Get requested function name and function data required by id

        if func_id > 0:
            relevant_functions = [functions_data[func_id - 1]]
        elif func_id == 0:  # Routes
            relevant_functions = []
            json_file_path = os.path.join(folder_path, "627main.json")
            route_data = V_LIBRARY.get_data(json_file_path, "Routes")
            route_graph = V_LIBRARY.map_route(route_data, folder_path)
        else:
            # All graph
            relevant_functions = functions_data
            func_id = "All"

        # Set graph file name
        graph_file_name = f"{func_id}.{graph_ext}"
        graph_func_file_path = os.path.join(folder_path, "graphs", graph_file_name)

        # if json_file_path.endswith("security.json"):
        # Extract tainted variables data
        # Create tainted variable graph after base graph drawn
    except FileNotFoundError as e:
        print("Backend JSON FileNotFound", e)
        # Handle case when JSON file is not found
        print(f"JSON file not found for {filename}")
        return f"JSON file not found for {filename}"

    # Create file-function mapping, preserving function id
    file_function_map = file_func_map_to_directory_structure(function_names)

    # Get variable trace queries

    security_query_csv = os.path.join(folder_path, "security.csv")
    queries, fq = get_variable_trace_query(security_query_csv)
    trace_values = dataframe_to_dictionary(queries, "queryName", "list", ["edges", "generate_functions"])

    # Check if the HTML file exists for the specified func_name
    if not regenerate and os.path.isfile(graph_func_file_path):
        # HTML file for the requested function exists
        all_rendered = os.path.exists(os.path.join(folder_path, "graphs", f"{func_id}.{graph_ext}"))
        return (
            f"/{graph_func_file_path}",
            file_function_map,
            func_id,
            trace_values,
            all_rendered,
        )
    elif GRAPH_LIBRARY == "python_viz":
        if route_graph:
            route_graph.write_html(
                os.path.join(folder_path, "Routes.html"), notebook=False
            )
        V_LIBRARY.generate_graph(functions_data, folder_path)
    else:  # Graphviz
        # Main graph

        dot_graph = V_LIBRARY.create_graph(
            rank="TB", engine="dot"
        )  # Set rankdir to 'TB' for top-to-bottom layout
        try:
            if route_graph and func_id == 0:  # only generate when requested
                # Insert route nodes into main graph
                dot_graph.subgraph(route_graph)
                # Render route graph as svg

                route_graph.render(
                    filename=str(func_id),
                    directory=os.path.join(folder_path, "graphs"),
                    cleanup=True,
                    format="svg",
                    engine="neato",
                )
                # route_graph.save(f'{graph_func_file_path}.dot')

                return (
                    f"/{graph_func_file_path}",
                    file_function_map,
                    func_id,
                    trace_values,
                    all_rendered,
                )
            dot_graph.subgraph(
                V_LIBRARY.generate_graphviz_dot(relevant_functions, folder_path)
            )
            dot_graph.save(filename=graph_func_file_path + ".dot")
            render_graph(
                dot_graph,
                filename=f"{func_id}",
                directory=os.path.join(folder_path, "graphs"),
                cleanup=True,
                format="svg",
                engine="dot",
            )
            if func_id == "All":
                all_rendered = True

        except CalledProcessError as e:
            print("Backend CalledProcessError:", e)
        except FileNotFoundError as e:
            print("Backend FileNotFound:", e)
            pass
        except TimeoutError as e:
            print("Backend Render graph timeout:", e)
            if func_id != "All":
                return e.message

    return (
        f"/{graph_func_file_path}",
        file_function_map,
        func_id,
        trace_values,
        all_rendered,
    )


@timeout(300)
def render_graph(graph, filename, directory, cleanup, format="svg", engine="neato"):
    graph.render(
        filename=filename,
        directory=directory,
        cleanup=cleanup,
        format=format,
        engine=engine,
    )
