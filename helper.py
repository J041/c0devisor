import os, ast, pandas
from app import app, CLASS_颜色, FUNCTION_颜色


def generate_vld(file_name):
    """Accepts a single php file and runs vld without execution on it."""
    vld_output = file_name.replace(".php", ".txt")
    os.system(
        f"php -d vld.active=1 -d vld.execute=0 '{file_name}' > '{vld_output}' 2>&1"
    )
    # TODO: Error handling of non-php files
    return vld_output


def get_self_filename(filepath, with_path=False):
    """Given a filepath, return the filename without extension
    if with_path is set to True, return the filepath with extension stripped
    """
    if with_path:

        filename = os.path.relpath(filepath, app.config["UPLOAD_FOLDER"])
        return os.path.splitext(filename)[0]

    else:
        filename = os.path.split(filepath)[-1]
        return filename.rsplit(".", 1)[0]


def file_func_map_to_directory_structure(function_names):
    """
    Convert a list of (function, filepath) to a directory structure
    """
    file_function_map = dict()
    for id, f in enumerate(function_names):
        temp_pointer = file_function_map
        if f[1] is None:
            directories = [None]
        else:
            directories = f[1].split("/")
            directories[-1] = "&" + directories[-1]
        for dir in directories[:-1]:
            temp_pointer = temp_pointer.setdefault(dir, dict())

        if directories[-1] not in temp_pointer.keys():
            temp_pointer[directories[-1]] = []
        if "." in f[0]:
            temp_pointer[directories[-1]].append((f[0], id, CLASS_颜色))
        else:
            temp_pointer[directories[-1]].append((f[0], id, FUNCTION_颜色))
    return file_function_map


def get_variable_trace_query(csv_handle, filter_queries=None):
    """
    filter_queries: accepts a list of query names as strings to filter
    returns queries and the filtered queries or None if no list was passed
    """
    def_queries = pandas.DataFrame(
        columns=[
            "queryName",
            "variable",
            "line",
            "source_function",
            "source_file",
            "sink",
            "sanitization",
            "edges",
            "generate_functions",
            "taint_count",
        ]
    )
    try:
        if os.path.exists(csv_handle):
            queries = pandas.read_csv(csv_handle, sep=";")
            queries = queries.astype({"queryName": str})
            for i in range(len(queries)):
                for col_index in [5, 6, 7, 8]:
                    queries.iat[i, col_index] = tuple(
                        ast.literal_eval(queries.iat[i, col_index])
                    )
            if filter_queries is not None:
                filter_queries = queries[queries["queryName"].isin(filter_queries)]
            return queries, filter_queries

    except (IndexError, ValueError) as e:
        print("HELPER get_variable_trace_query\n", e)
    return def_queries, def_queries


def dataframe_to_dictionary(df, key, value_type, exclude_cols=None):
    if exclude_cols is None:
        exclude_cols = []
    trace_values = (
        df.loc[:, ~df.columns.isin(exclude_cols)].set_index(key).T.to_dict(value_type)
    )
    return trace_values