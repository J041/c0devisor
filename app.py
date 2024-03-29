#! ========================================================================== #
#!                          External library Imports
#! ========================================================================== #

from flask import (
    Flask,
    render_template,
    flash,
    redirect,
    url_for,
    send_from_directory,
    request,
    make_response,
)
from flask_sse import sse

# Python modules
import os, re, json, shutil, logging, rq
from graphviz.backend.execute import CalledProcessError  # Exception handling

from werkzeug.utils import secure_filename

#! ========================================================================== #
#!                        Application Config Definitions
#! ========================================================================== #
app = Flask(__name__)
app.secret_key = "supersecretkey"
app.config["REDIS_URL"] = "redis://localhost"
app.register_blueprint(sse, url_prefix="/status")

UPLOAD_FOLDER = "uploads/user_upload"
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["UPLOAD_EXTENSIONS"] = [".php", ".zip"]

CLASS_颜色 = "#CE93D8"
FUNCTION_颜色 = "#9FA8DA"
FILE_颜色 = "#FFCC80"

#! ========================================================================== #
#!                          Custom module imports
#! ========================================================================== #

import Backend as be
import security
import helper
import worker

#   Visualization modules
import dotgraph


# Change graph library here ---------------------------
GRAPH_LIBRARY = "dotgraph"  # python_viz OR dotgraph

VISUALIZATIONS_LIBRARY = {
    "dotgraph": (dotgraph, "svg"),
}
V_LIBRARY = VISUALIZATIONS_LIBRARY[GRAPH_LIBRARY][0]
graph_ext = VISUALIZATIONS_LIBRARY[GRAPH_LIBRARY][1]


#! ========================================================================== #
#!                              Enable Logging
#! ========================================================================== #


# logging.basicConfig(filename="apptest.txt")
class LoggingFilter(logging.Filter):
    def filter(self, record):
        return "GET /status" not in record.getMessage()


log = logging.getLogger("werkzeug")
log.addFilter(LoggingFilter())


#! ========================================================================== #
#!                               Task Queue
#! ========================================================================== #
high = rq.Queue("high", connection=worker.conn)
medium = rq.Queue("medium", connection=worker.conn)
low = rq.Queue("low", connection=worker.conn)



@app.route("/")
def index():
    cookie = request.cookies.get("folder", "[]")
    uploaded_files = json.loads(cookie)
    return render_template("index.html", uploaded_files=uploaded_files, show_html=False)


@app.route("/status/<key>", methods=["GET"])
def get_status(key):
    # print("connect", key)
    # sse.publish({"message": f"Hello! {key}" }, type='update')
    try:
        job = rq.job.Job.fetch(key, connection=worker.conn)
    except rq.exceptions.NoSuchJobError:
        response = make_response({"message": "Request expired or failed"})
        response.status = 410  # Accepted
        return response
    job_status = job.get_status(refresh=True)
    if job_status == "failed" or job.result == -1:
        response = make_response({"message": job.exc_info})
        response.status = 404
        return response
    # elif job_status == "cancelled":
    elif job_status != "finished":
        response = redirect(url_for("index"))
        response.status = 202  # Accepted
        return response

    dst_folder = job.result

    # Redirect to index if upload successful
    # flash("File uploaded successfully", "success")

    existing_folders = json.loads(request.cookies.get("folder", "[]"))

    #! problem

    new_folder = os.path.split(dst_folder)[-1]

    if new_folder not in existing_folders:
        existing_folders.append(new_folder)
        response = make_response({"new": new_folder, "index": len(existing_folders)})
    else:
        response = make_response(
            {"new": new_folder, "index": existing_folders.index(new_folder) + 1}
        )
    response.set_cookie("folder", json.dumps(existing_folders))

    response.status = 201
    return response


@app.route("/upload", methods=["POST"])
def upload_file():
    file_obj = request.files.get("file")
    if file_obj is None:
        response = redirect(url_for("index"))
        response.status = 400
        return response
    filename = secure_filename(file_obj.filename)
    file_ext = (
        split_name_ext[1]
        if len(split_name_ext := os.path.splitext(filename)) == 2
        else ""
    )
    if file_ext not in app.config["UPLOAD_EXTENSIONS"]:
        response = redirect(url_for("index"))
        response.status = 400
        return response

    # Crafting dst folder name
    folder_name = helper.get_self_filename(filename)
    destination_folder = os.path.join(app.config["UPLOAD_FOLDER"], folder_name)
    filepath = os.path.join(destination_folder, filename)
    # ! Create destination folder and save .zip / .php file
    os.makedirs(destination_folder, exist_ok=True)
    file_obj.save(filepath)

    # result_ttl: time to hold on to the result for
    # Enqueue based on size and expected time taken
    if (os.stat(filepath).st_size < 100 * 1024):
        job = high.enqueue_call(func=be.resubmit_file, args=(filepath,), result_ttl=50, timeout=-1)
    elif (file_ext == ".php" or os.stat(filepath).st_size < 1024 * 1024):
        job = medium.enqueue_call(func=be.resubmit_file, args=(filepath,), result_ttl=100, timeout=-1)
    else:
        job = low.enqueue_call(func=be.resubmit_file, args=(filepath,), result_ttl=86400, timeout=-1)

    response = make_response(job.get_id())
    response.status = 202
    return response


# app.py
@app.route("/view_files")
def view_files():
    # When the user wants to see the files they have uploaded
    # uploaded_files = os.listdir(app.config["UPLOAD_FOLDER"])
    cookie = request.cookies.get("folder", "[]")
    uploaded_files = json.loads(cookie)

    # Code will just return the entire directory
    return render_template(
        "view_files.html", uploaded_files=uploaded_files, show_html=False
    )



@app.route("/resubmit/<del_filename>", methods=["POST"])
def resubmit(del_filename):
    # need add check if input is empty
    file_obj = request.files.get("file")
    if file_obj is None:
        response = redirect(url_for("index"))
        response.status = 400
        return response
    filename = secure_filename(file_obj.filename)
    file_ext = (
        split_name_ext[1]
        if len(split_name_ext := os.path.splitext(filename)) == 2
        else ""
    )
    if file_ext not in app.config["UPLOAD_EXTENSIONS"]:
        response = redirect(url_for("index"))
        response.status = 400
        return response

    # Regex pattern to get folders from response header
    regex_pattern = re.compile(r"\\\"(.+?)\\\"")
    existing_folders = []
    try:
        delete_response = delete_file(del_filename)
        if delete_response.status ==  403:
            # TODO: send error to frontend
            return delete_response
        updated_cookies = delete_response.headers.getlist(
            "Set-Cookie"
        )  # ['f','o']-> ['f]
        existing_folders = re.findall(regex_pattern, updated_cookies[0])
    finally:

        # Crafting dst folder name
        folder_name = helper.get_self_filename(filename)
        destination_folder = os.path.join(app.config["UPLOAD_FOLDER"], folder_name)
        filepath = os.path.join(destination_folder, filename)
        # ! Create destination folder and save .zip / .php file
        os.makedirs(destination_folder, exist_ok=True)
        file_obj.save(filepath)
        # result_ttl: time to hold on to the result for
        # Enqueue based on size and expected time taken
        if (os.stat(filepath).st_size < 100 * 1024):
            job = high.enqueue_call(be.resubmit_file, args=(filepath,), result_ttl=50, timeout=-1)
        elif (file_ext == ".php" or os.stat(filepath).st_size < 1024 * 1024):
            job = medium.enqueue_call(be.resubmit_file, args=(filepath,), result_ttl=100, timeout=-1)
        else:
            job = low.enqueue_call(be.resubmit_file, args=(filepath,), result_ttl=600, timeout=-1)

        response =  make_response(job.get_id())
        response.set_cookie("folder", json.dumps(existing_folders))
        response.status = 202
        return response


@app.route("/view_graph/<filename>/<func_id>/regenerate")
@app.route("/view_graph/<filename>/<func_id>", methods=["GET", "POST"])
@app.route("/view_graph/<filename>/regenerate")
@app.route("/view_graph/<filename>")
def view_graph(filename, func_id="0"):
    # ! Convert function id to integer
    func_id = int(func_id) if func_id.lstrip("+-").isdigit() else 0

    # ! Validate folder accessibility
    cookie = request.cookies.get("folder", "[]")
    accessible_folders = json.loads(cookie)
    if filename not in accessible_folders:
        flash("No such folder found", "danger")
        return redirect(url_for("index"))

    # Construct paths

    # ? Relative folder path
    # ? Append '/' at the beginning of string for html links
    folder_path = os.path.join(
        app.config["UPLOAD_FOLDER"], filename
    )  # Has no root symbol
    to_regenerate_graph = "regenerate" in request.path
    result = be.view_graph(filename, func_id, folder_path, to_regenerate_graph)
    if type(result) is str:
        flash(result, "danger")
        return redirect(url_for("view_files"))
    
    return render_template(
        "view_graph.html",
        html_file_path=result[0],
        file_function_map=result[1],
        filename=filename,
        active_func_id=result[2],
        trace_values=result[3],
        all_rendered=result[4],
    )


@app.route("/view_individual_graph")
def view_individual_graph():
    filepath = request.args.get("filepath")
    filename = request.args.get("filename")
    return render_template(
        "view_individual_graph.html", html_file_path=filepath, filename=filename
    )


@app.route("/delete_file/<filename>")
def delete_file(filename):
    existing_folders = json.loads(request.cookies.get("folder", "[]"))
    response = redirect(url_for("view_files"))
    # Check if user authorized to delete
    try:
        existing_folders.index(filename)
    except ValueError:
        print("Requested folder for deletion does not exist.")
        flash("Requested folder for deletion does not exist.")
        response.status = 403
        return response
    # Attempt to delete file
    path = app.config["UPLOAD_FOLDER"] + "/" + filename
    try:
        shutil.rmtree(path)
    except FileNotFoundError as e:
        print(e)
        pass

    flash("File deleted successfully", "success")

    # Remove all occurrences of the value 3 from the list
    existing_folders = [x for x in existing_folders if x != filename]
    response.set_cookie("folder", json.dumps(existing_folders))

    return response


@app.route("/uploads/user_upload/<path:filename>")
def uploaded_file(filename):
    # Validate folder accessibility
    cookie = request.cookies.get("folder", "[]")
    accessible_folders = json.loads(cookie)
    folder_name = filename.split("/")[0]
    if folder_name not in accessible_folders:
        flash("Access Denied", "danger")
        return redirect(url_for("index"))

    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


@app.route("/view_graph/<filename>/submit_security_forms/<key>", methods=["GET"])
@app.route("/view_graph/<filename>/submit_security_forms", methods=["POST"])
def submit_security_forms(filename, key=None):

    # Validate folder accessibility
    cookie = request.cookies.get("folder", "[]")
    accessible_folders = json.loads(cookie)
    if filename not in accessible_folders:
        flash("No such folder found", "danger")
        return redirect(url_for("index"))

    # Construct paths
    # Relative folder path
    # Append '/' at the beginning of string for html links
    folder_path = os.path.join(
        app.config["UPLOAD_FOLDER"], filename
    )  # Has no root symbol
    security_query_csv = os.path.join(folder_path, "security.csv")

    # Access the form data
    query_name = request.form.get("queryName", None)
    source_var = request.form.get("sourceInput1")
    source_line = request.form.get("sourceInput2")
    source_function_name = request.form.get("sourceInput3")
    source_filepath = request.form.get("sourceInput4")
    sink = [sink_func.strip().lower() for sink_func in request.form.get("sinkInput").split(",")]
    sanitization = [
        sani_func.strip().lower()
        for sani_func in request.form.get("sanitizationInput").split(",")
    ]

    # Check if input is empty -> incase i need but if not please delete :)
    if not source_var:
        flash("Variable Name is empty!", "danger")
        return redirect(url_for("view_graph", filename=filename))
    tracing_superglobal_or_function = source_var.split("[")[0] in security.SUPERGLOBAL_LIST or "()" in source_var
    # if not source_line:
    #     flash("Line Number is empty!", "danger")
    #     return redirect(url_for("view_graph", filename=filename))
    # if not source_function_name:
    #     flash("Source Function is empty!", "danger")
    #     return redirect(url_for("view_graph", filename=filename))
    if not source_filepath:
        if tracing_superglobal_or_function:
            source_filepath = folder_path
        else:
            flash("Source File is empty!", "danger")
            return redirect(url_for("view_graph", filename=filename))
    else:
        source_filepath = (
            os.path.join(app.config["UPLOAD_FOLDER"], source_filepath) + ".php"
        )
    ###

    # if source_filepath == source_function_name:
    #     source_function_name = "(null)"
    # prefix provided file path with upload folder path
    # source_filepath = source_filepath.strip("/")


    queries, fq = helper.get_variable_trace_query(security_query_csv)

    if query_name is None:
        query_name = len(queries) + 1

    if query_name in queries["queryName"].values:
        flash("Query Name exists", "danger")
        return redirect(url_for("view_graph", filename=filename))

    queries.loc[len(queries) + 1] = [
        query_name,
        source_var,
        source_line,
        source_function_name,
        source_filepath,
        tuple(sink),
        tuple(sanitization),
        tuple(),
        tuple(),
        0
    ]

    if queries.duplicated(
        subset=[
            "variable",
            "line",
            "source_function",
            "source_file",
            "sink",
            "sanitization",
        ],
        keep="first",
    ).all():
        flash("Trace already exists!", "danger")
        return redirect(url_for("view_graph", filename=filename))
    # Initialize variable_trace as an empty dictionary
    variable_trace = {}

    # TODO: sanitize input and check function exists

    # Run variable tracing
    try:
        # Getting variable trace
        if (tracing_superglobal_or_function):
            variable_trace = security.superglobal_getter(
                source_var, sink, sanitization, source_filepath, source_line
            )
        # elif "$" not in source_var and "()" not in source_var:
        #     flash(f"Invalid Source Input", "danger")
        #     return redirect(url_for("view_graph", filename=filename))

        else:
            # if len(source_function_name.split(".")) > 1:
            #     source_function_name = source_function_name.split(".")[-1]
            v, t = security.funcsecurity_prepare(
                source_var,
                source_line,
                sink,
                sanitization,
                source_filepath,
                function_name=source_function_name,
            )

            variable_trace[source_filepath] = [v]

    except security.VariableNotFound as e:
        flash(f"An error occurred: {str(e)}", "danger")
        return redirect(
            url_for("view_graph", filename=filename)
        )  # Redirect to the page where the form is displayed
    except RecursionError as e:
        # Max recursion depth exceeded
        print("Error", e)
        flash(f"An error occurred: Query Invalid", "danger")
        return redirect(
            url_for("view_graph", filename=filename)
        )

    # List of all functions data
    functions_data = []
    # List of all functions names to populate the function menu (Left sidebar)
    function_names = [("Routes", None)]

    # Route graph defaults to None, set on user request
    try:
        # Retrieve all function names and corresponding file as tuple
        json_file_path = os.path.join(folder_path, "func_file.json")
        with open(json_file_path, "r") as json_file:
            func_file_dict = json.load(json_file)
            function_names += [v for v in func_file_dict.values()]

        # Retrieve all function data
        json_file_path = os.path.join(folder_path, "functions.json")
        with open(json_file_path, "r") as json_file:
            functions_data = V_LIBRARY.get_data(json_file_path, "function")

    except FileNotFoundError:
        # Handle case when JSON file is not found
        print(f"JSON file not found for {filename}")
        flash(f"JSON file not found for {filename}", "danger")
        return redirect(url_for("view_files"))
    # Create file-function mapping, preserving function id
    file_function_map = helper.file_func_map_to_directory_structure(function_names)

    if variable_trace is None:
        # handle error
        return 
    # TODO: verify default value returned
    security_json_path = os.path.join(folder_path, "security.json")
    with open(security_json_path, "w") as json_dump:
        json_dump.write(json.dumps(variable_trace, indent=2))


    new_edges, functions_to_generate = V_LIBRARY.security(security_json_path)
    queries.at[len(queries), "edges"] += tuple(new_edges)
    queries.at[len(queries), "taint_count"] = len(new_edges)
    queries.at[len(queries), "generate_functions"] = functions_to_generate
    queries.to_csv(security_query_csv, sep=";", mode="w", index=False)
    
    graph_directory = os.path.join(folder_path, "graphs")
    security_graph = V_LIBRARY.create_graph(rank="TB", strictness=True)
    relevant_functions = []
    source_func_id = None 
    for func, file in functions_to_generate:
        for f_id in range(len(function_names)):
            if function_names[f_id][0] == func and function_names[f_id][1] == file:
                relevant_functions.append(functions_data[f_id - 1])
                break
    
    
    security_graph.subgraph(V_LIBRARY.generate_graphviz_dot(relevant_functions, folder_path, {"Exports": False, "Depends": False}))
    for i, edges in enumerate(new_edges):
        for edge in edges:
            if len(edge) < 3:
                continue
            if edge[1] is not None:
                V_LIBRARY.add_edge(security_graph, edge[0], edge[1], edge[2])
                if edge[2] == "Sanitized":
                    continue

            V_LIBRARY.add_node(security_graph,edge[0],attribute="Tainted_node")
            
    try:
        security_graph.render(
            "security",
            directory=graph_directory,
            cleanup=True,
            format="svg",
            engine="dot",
        )
    except FileNotFoundError as e:
        print("Cleanup", e)
    except CalledProcessError as e:
        print(e)

    trace_values = helper.dataframe_to_dictionary(
        queries, "queryName", "list", ["edges", "generate_functions"]
    )
    for id in range(len(function_names)):
        if function_names[id][0] == source_function_name and function_names[id][1] == helper.get_self_filename(source_filepath, True):
            source_func_id = id
            break

    return render_template(
        "view_graph.html",
        html_file_path=f"/{os.path.join(graph_directory, 'security')}.svg",
        file_function_map=file_function_map,
        filename=filename,
        active_func_id=source_func_id,
        trace_values=trace_values,
    )


@app.route("/view_graph/<filename>/security_view", methods=["POST"])
def security_view(filename):
    # Validate folder accessibility
    cookie = request.cookies.get("folder", "[]")
    accessible_folders = json.loads(cookie)
    if filename not in accessible_folders:
        flash("No such folder found", "danger")
        return redirect(url_for("index"))

    keys_map = request.form.get("activeKeys")
    if keys_map is None:
        return redirect(url_for("view_graph", filename=filename))
    keys_taint = json.loads(keys_map)
    keys = keys_taint.keys()
    # Construct paths

    # Relative folder path
    # Append '/' at the beginning of string for html links
    folder_path = os.path.join(
        app.config["UPLOAD_FOLDER"], filename
    )  # Has no root symbol
    security_query_csv = os.path.join(folder_path, "security.csv")

    queries, filter_queries = helper.get_variable_trace_query(security_query_csv, keys)
    edges_group = [e for edge_group in filter_queries["edges"].tolist() for e in edge_group]
    functions_to_generate = [func_file_ref for outer_tuple in filter_queries["generate_functions"].tolist() for func_file_ref in outer_tuple ]

    # List of all functions data
    functions_data = []
    # List of all functions names to populate the function menu (Left sidebar)
    function_names = [("Routes", None)]

    # Route graph defaults to None, set on user request
    try:
        # Retrieve all function names and corresponding file as tuple
        json_file_path = os.path.join(folder_path, "func_file.json")
        with open(json_file_path, "r") as json_file:
            func_file_dict = json.load(json_file)
            function_names += [v for v in func_file_dict.values()]

        # Retrieve all function data
        json_file_path = os.path.join(folder_path, "functions.json")
        with open(json_file_path, "r") as json_file:
            functions_data = V_LIBRARY.get_data(json_file_path, "function")

    except FileNotFoundError:
        # Handle case when JSON file is not found
        print(f"JSON file not found for {filename}")
        flash(f"JSON file not found for {filename}", "danger")
        return redirect(url_for("view_files"))

    # Create file-function mapping, preserving function id
    file_function_map = helper.file_func_map_to_directory_structure(function_names)

    # TODO: verify default value returned
    # TODO: implement for pyviz

    security_graph = V_LIBRARY.create_graph(rank="TB", strictness=True)
    # Add variable tracing edges
    for k in keys:
        if keys_taint[k].isdigit():
            keys_taint[k] = int(keys_taint[k])
            edges_group_requested = edges_group
            if keys_taint[k] != 0:
                for i in range(len(edges_group_requested)):
                    if i != keys_taint[k] - 1:
                        edges_group_requested[i] = []
        else:
            # error
            continue
        for i, edges in enumerate(edges_group_requested):
            for edge in edges:
                if len(edge) < 3:
                    continue
                V_LIBRARY.add_edge(security_graph, edge[0], edge[1], edge[2])

    graph_directory = os.path.join(folder_path, "graphs")

    # Map function to ID
    relevant_functions = []
    for func, file in functions_to_generate:
        for f_id in range(len(function_names)):
            if function_names[f_id][0] == func and function_names[f_id][1] == file:
                relevant_functions.append(functions_data[f_id - 1])
                break

    # Insert regular line nodes of functions
    security_graph.subgraph(
        V_LIBRARY.generate_graphviz_dot(relevant_functions, folder_path, {"Exports": False, "Depends": False}),
    )
    try:
        # Save as svg
        security_graph.render(
            "security",
            directory=graph_directory,
            cleanup=True,
            format="svg",
            engine="dot",
        )
    except FileNotFoundError as e:
            print(e)
            pass
    except CalledProcessError as e:
            print(e)
    trace_values = helper.dataframe_to_dictionary(
        queries, "queryName", "list", ["edges", "generate_functions"]
    )

    return render_template(
        "view_graph.html",
        html_file_path=f"/{os.path.join(graph_directory, 'security')}.svg",
        file_function_map=file_function_map,
        filename=filename,
        active_func_id=None,
        trace_values=trace_values,
    )


@app.route("/view_graph/<filename>/delete_security_form/<key>", methods=["POST"])
def delete_security_form(filename, key):
    active_func_id = request.form.get("activeFuncId", '0')

    folder_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    # Get variable trace queries
    security_query_csv = os.path.join(folder_path, "security.csv")
    queries, fq = helper.get_variable_trace_query(security_query_csv)

    # Remove specified query with provided query name and write to file
    queries = queries.loc[queries.queryName != key, :]
    queries.to_csv(security_query_csv, sep=";", mode="w", index=False)

    # Return success/failure

    flash(f"Query {key} deleted.", "primary")
    return redirect(url_for("view_graph", filename=filename, func_id=active_func_id))


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
