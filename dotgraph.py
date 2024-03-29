from copy import copy
import json
from flask import url_for
import graphviz
import html
import os
from app import app

color_dict = {
    "ID": "#e74c3c",
    "Name": "#2ecc71",
    "Depends": "#e67e22",
    "Exports": "#9b59b6",
    "Line": "#03A9F4",
    "Tainted": "#FF0000",
    "Sanitized": "#FFFF00",
    "Variable_Tacking_Function_call": "#000000",
    "Tainted_node": "#FF0000:#03A9F4",
    "LinesEnd": "#26A69A",
    
    "LinesIf": "#66BB6A",
    "LinesElse": "#66BB6A",
    
    "LinesFor": "#9CCC65",
    
    "LinesDo": "#D4E157",
    "LinesSwitch": "#D4E157",
    "LinesCase": "#D4E157",
    
    "LinesWhile": "#EC407A",
    "Default": "#FFFFFF"
}



def create_graph(name=None, engine="dot", rank="TB", strictness=False):
    return graphviz.Digraph(name, format='svg', graph_attr={'rankdir': rank, 'overlap': "false"}, engine=engine, strict=strictness)


def add_node(dot, node_id, node_content=None, attribute="Default", rank=None, url=None):
    # node_content = html.escape(node_content)
    # node_id = html.escape(node_id)

    # html.escape when &, <, and > are in used, prevent content from interfering with .dot syntax

    if node_content is not None and len(node_content) > 16384:
        node_content = "<<b>Truncated Content, refer to file for exact content:</b>"+html.escape(node_content[:100])+'>'
    if url:
        node_content = f"<<u>{html.escape(node_content)}</u>>"
        
    if rank:
        dot.node(
            node_id, label=node_content, 
            color=color_dict.get(attribute), style='filled', fillcolor=color_dict.get(attribute), 
            shape='box', rank=rank, URL=url, target="_parent")
    else:
        dot.node(node_id, label=node_content, 
            color=color_dict.get(attribute), style='filled', fillcolor=color_dict.get(attribute), 
            shape='box', URL=url, target="_parent")


def add_edge(dot, from_node, to_node, attribute):
    # from_node = html.escape(from_node)
    # to_node = html.escape(to_node)
    dot.edge(from_node, to_node, color=color_dict.get(attribute), dir='forward')


def generate_graphviz_dot(functions, folder_path, options=None):
    render_export = True
    render_dependency = True
    dot = graphviz.Digraph(format='svg', graph_attr={'rankdir': 'TB'})  # Set rankdir to 'TB' for top-to-bottom layout
    if options is not None:
        render_export = options.get("Exports", True)
        render_dependency = options.get("Depends", True)

    for func in functions:
        function_graph = graphviz.Digraph(name=func["Name"], format='svg', graph_attr={'rankdir': "TB"})

        node_id = str(func["ID"])
        node_func_name = func["Name"]
        url = f"/view_graph/{os.path.split(folder_path)[-1]}/{func['ID']}"
        
        add_node(function_graph, node_id, node_id, "ID", rank='source')  # Color for "ID" attribute
        add_node(function_graph, node_func_name, graphviz.escape(node_func_name), "Name", rank='same', url=url)  # Color for "Name" attribute

        add_edge(function_graph, node_id, node_func_name, "Depends")

        if render_dependency:
            for dependency in func.get("Depends", []):
                dependency_name = f"{dependency[0]}"
                add_node(function_graph, dependency_name, dependency_name, "Depends", rank='sink')
                add_edge(function_graph, node_func_name, dependency_name, "Depends")

        if render_export:
            for exports in func.get("Exports", []):
                exports_name = f"{exports}"
                add_node(function_graph, exports_name, exports_name, "Exports", rank='sink')
                add_edge(function_graph, node_func_name, exports_name, "Exports")
        
        map_lines(function_graph, node_func_name, func.get("Lines", {}), (node_func_name, node_id), folder_path)
        try:
            dot.subgraph(function_graph)
            function_graph.render(filename=f"{func['ID']}",directory=os.path.join(folder_path, "graphs"), cleanup=True, format='svg', engine='dot')
        except graphviz.backend.execute.CalledProcessError as e:
            print("Function: ", func["ID"],"Error:", e)
            function_graph.save(filename=f"{func['ID']}", directory=os.path.join(folder_path, "error"))
        except FileNotFoundError:
            pass
        function_graph.clear()
    return dot

def map_lines(dot, parent_name, lines_data, function_name_id, folderpath):
    # Connect Lines sequentially to the function name
    prev_line_node = [parent_name]
    line_number = None
    
    # Colour control structures
    control_block_count = 0
    keywords = [k.replace("Lines", '').lower() for k in color_dict.keys() if k.startswith("Lines")]

    
    for line_number, line_content in lines_data.items():
        if type(line_content) == dict and ('-if' in line_number.lower() or '-else' in line_number.lower()):
            branch_last_node = map_lines(dot, prev_line_node[0], line_content, function_name_id,folderpath)
            for b in branch_last_node:
                if b not in prev_line_node:
                    prev_line_node.append(b)
            continue

        elif type(line_content) == dict and '-for' in line_number:
            prev_line_node = map_lines(dot, prev_line_node[0], line_content, function_name_id,folderpath)
            continue

        elif type(line_content) == dict and ('-case' in line_number):
            branch_last_node = map_lines(dot, prev_line_node[0], line_content, function_name_id,folderpath)
            for b in branch_last_node:
                if b not in prev_line_node:
                    prev_line_node.append(b)
            continue

        elif type(line_content) == dict and '-do' in line_number:
            prev_line_node = map_lines(dot, prev_line_node[0], line_content, function_name_id,folderpath)
            continue

        elif type(line_content) == dict and '-switch' in line_number:
            prev_line_node = map_lines(dot, prev_line_node[0], line_content, function_name_id,folderpath)
            continue
        
        elif type(line_content) == dict and ('-while' in line_number):
            branch_last_node = map_lines(dot, prev_line_node[0], line_content, function_name_id,folderpath)
            for b in branch_last_node:
                if b not in prev_line_node:
                    prev_line_node.append(b)
            continue
        
        line_node = f"{line_number}:\t{line_content[0]}"
        line_node = graphviz.nohtml(line_node)
        line_id = f"{function_name_id[0]}-{line_number}"
        stripped_line_value = line_content[0].strip().lower()
        
        # Default node type
        node_type = "Line"
        if line_number == list(lines_data.keys())[0]:
            for keyword in keywords:
                if stripped_line_value.startswith(keyword):
                    # Assign the corresponding node_type
                    node_type = f"Lines{keyword.capitalize()}"
                    control_block_count += 1
                    break  # Stop checking further keywords once a match is found    

        # Check if end of func
        if '}' in stripped_line_value and control_block_count > 0:
            node_type = "LinesEnd"  
            control_block_count -= 1
       
        # Check if func name in line content
        # Might need add .lower()
        url = None
        if len(line_content) > 1:
            for func in line_content[1::]:
                url = url_for('view_graph', filename=os.path.split(folderpath)[-1], func_id=func)
        add_node(dot, line_id, line_node, node_type, rank='sink', url=url)

        for branch in prev_line_node:
            add_edge(dot, branch, line_id, "Line")
        prev_line_node = [line_id]
    return prev_line_node


def map_route(route_data = None, folder_path = ""):
    route_graph = create_graph("Routes", engine="neato", strictness=True)
    
    if route_data is None:
        return route_graph
    
    for r in route_data:
        if type(r) is str:
            add_node(route_graph, r.split(':')[0], r, "Name")
        elif "url" in r.keys():
            url = url_for('view_graph', filename=os.path.split(folder_path)[-1], func_id=r["url"][1])
            add_node(route_graph, r["url"][0], graphviz.escape(r["url"][0]), "Name", url=url)
            for link in r["source"]:
                node_id = graphviz.escape(link["Url"])
                node_content = graphviz.nohtml(f'{link["Method"]} {link["Url"]}')
                add_node(route_graph, node_id, node_content, "Depends")
                add_edge(route_graph, r["url"][0], node_id, "Depends")
            for link in r["destination"]:
                node_id = graphviz.escape(link["Url"])
                node_content = graphviz.nohtml(f'{link["Method"]} {link["Url"]}')
                add_node(route_graph, node_id, node_content, "Exports")
                add_edge(route_graph, r["url"][0], node_id, "Exports")
    return route_graph    


def get_data(file_path, func_name="function"):
    try:
        with open(file_path, "r") as json_file:
            return json.load(json_file)[func_name]
    except FileNotFoundError:
        # logging.error(f"Error: File not found - {file_path}")
        raise
    except json.JSONDecodeError:
        # logging.error(f"Error: Incorrect JSON format - {file_path}")
        pass
    except KeyError as e:
        # logging.error(f"Error: Key {str(e)} not found - {file_path}")
        pass
    except TypeError as e:
        # logging.error(f"Error: Incorrect file {str(e)} format provided - {file_path}")
        pass

# Trace tainted variables on a function graph
def trace_tainted(current, functions_called, current_node=None, sanitized=False):
    edge_type = "Tainted" # Default edge
    if sanitized:
        edge_type = "Sanitized"
    # Get tainted function and line number to reconstruct id
    tainted_func, *tainted_lines = current.strip(':').split(':')
    source_id = f"{tainted_func}-{tainted_lines[0]}"
    edges = []
    # Link across functions when function call occurs
    if current_node:

        edges.append((current_node, source_id, "Variable_Tacking_Function_call"))
        current_node = None

    # Loop through tainted lines
    for i in range(0, len(tainted_lines)):
        source_id = f"{tainted_func}-{tainted_lines[i]}"
        # Jump to next function, assume functions_called is ordered
        if source_id.endswith('S'):
            # Sanitized value
            source_id = source_id.strip('S')
            edge_type = "Sanitized"
            sanitized = True
        if 'F' in tainted_lines[i]:
            t_line, function_jump = tainted_lines[i].strip('S').split('F', 1)
            source_id = f"{tainted_func}-{t_line}"
            # Returns last node to join function return to parent/caller scope
            for function_index in range(len(copy(functions_called))):
                if functions_called[function_index].split(':', 1)[0] == function_jump:
                    function_end_node, new_edges = trace_tainted(functions_called.pop(function_index), functions_called, source_id, sanitized)
                    edges.extend(new_edges)
                    break
            else:
                function_end_node = source_id
            edges.append((function_end_node, source_id, "Variable_Tacking_Function_call"))
            destination_id = source_id
        
        if (i+1 < len(tainted_lines)):
            destination_id = tainted_func + '-' + tainted_lines[i+1].strip('S').split('F', 1)[0]
            edges.append((source_id, destination_id, edge_type))

        
    else:
        # If only 1 line in function
        if (len(tainted_lines) == 1):
            destination_id = tainted_func + '-' + tainted_lines[0].strip('S').split('F', 1)[0]
        edges.append((destination_id, None, edge_type))
    return destination_id, edges


def security(security_json):
    """ Generates security graph as svg in same file path as provided security json file
        function_data: list of functions data generated by backend
    """
    with open(security_json, "r") as json_file:
        security_tracking = json.load(json_file)

    # Create security graph 
    edges_group = []
    generated_functions = set() # track generated functions
    for file in security_tracking.keys():
        for function_group in security_tracking[file]:
            file = file.replace(app.config["UPLOAD_FOLDER"]+'/', '').replace('.php', '')
            for key in function_group.keys():
                tainted_func_lines, *functions_called = function_group[key]

                for f in functions_called:
                    generated_functions.add((f.split(':')[0], file))
                generated_functions.add((tainted_func_lines.split(':')[0], file))
                
                tainted_func_lines = tainted_func_lines.replace("(null)", file)
                # Begin tracing tainted variables 
                end_node, new_edges = trace_tainted(tainted_func_lines, functions_called)
                if len(new_edges) != 0:
                    edges_group.append(new_edges)

    edges_group = [list(x) for x in set(tuple(x) for x in edges_group)]
    return edges_group, generated_functions
