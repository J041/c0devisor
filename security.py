import re
import json
import os
import pathlib
import helper


USER_UPLOAD = "./uploads/user_upload"


SUPERGLOBAL_LIST = ["$_SERVER", "$_GET", "$_POST","$_FILES", "$_COOKIE", "$_SESSION","$_REQUEST", "$_ENV"]

# Exception thrown when variable is not in line provided
class VariableNotFound(Exception):
    def __init__(self, message):            
        super().__init__(message)

def funcsecurity(func_list, linked, func_to_php, vld_output = None, compiled_var = None, user_tainted = "", line_number = 0, func_name = "", sink_func_list = None, saniti_func_list = None, variable_dict = None, translation_dict = None, arg_pos = None, interfunc = False, filename = ""):
    # When getting the user's veriable from frontend, only need to feel up vld_output, compiled_var, user_tainted, line_number, func_name
    # Compiled_var translate !var to $var of the current function
    # user_tainted contains the tainted variable that the user chose
    # line_number is the line number the user chose 
    # translation_dict Translate the variable in this function to the one used to call it and is carried through different functions
    # variable_dict Contains variables associated with user defined variables
    # Temporary storage
    # Initialize compiled_var, variable dict, translation_dict, arg_pos if None
    if vld_output is None:
        vld_output = list()
    if compiled_var is None:
        compiled_var = dict()
    if variable_dict is None:
        variable_dict = dict()
    if translation_dict is None:
        translation_dict = dict()
    if arg_pos is None:
        arg_pos = dict()
    if sink_func_list is None:
        sink_func_list = list()
    if saniti_func_list is None:
        saniti_func_list = list()
    taint_dict = {}

    # Translated variable (!var)
    opcode_variable = ""

    #### Interfunction Tracking variables ####   
    pos = 0
    recv_pos = 0
    # Keep track of function calls
    interfunc_stack = []
    
    
    
    #### Interfunction Tracking variables END ####  

    # Sink Detector, states which line the sink function is found
    sink_line = "-1"
    sink_detected = False

    # Sanitization Detector, states if current php line contains a sanitization function, list of sanitized functions
    saniti_detected = False
    saniti_list = []
    # Indicates if the return value of a function is sanitized. Used when the function returns a value and need to indicate "S" to the assign variable
    sanitized_return = False

    # Indicate the class of a variable
    variable_class = ""

    # List of all global variables found in function
    global_list = []

    # Indicates if a global variable is being called in the same php line
    global_detected = False

    # States if the current function returns a sanitized value
    clean_return = "0"
    user_op_line = 0

    last_php = 0

    if not interfunc:
        for key in compiled_var.keys():
            if compiled_var[key] == user_tainted:
                opcode_variable = key
        

        current_php = 0
        
        translation_dict[func_name + "_" + user_tainted] = [func_name + "_" + user_tainted]
        #Find where the variable last appeared in the php line
        for line in vld_output:
            if line.split()[1].isdigit():
                current_php =  line.split()[0]
            
            if (current_php == str(line_number)) and (opcode_variable in line):
                
                if line.split()[1].isdigit():
                    # Kept this in because source function need, but very sure i removed this for a reason. Not sure what it was. I am so screwed
                    user_op_line = int(line.split()[1])
                else:
                    user_op_line = int(line.split()[0])
                
                last_php = current_php
                
                variable_dict[func_name + "_" + user_tainted] = [func_name + ":" + line_number + ":"]
                break
        if len(variable_dict) == 0:
            raise VariableNotFound("Variable not found!")
        
         # Find for source (Assign or Fetch)
        # for line in vld_output:
        #     if line.split()[1].isdigit():
        #         current_php =  line.split()[0]
                        
        #     if "ASSIGN" in line and re.search(opcode_variable+r"[^\d]", line):
        #         variable_dict[func_name + "_" + user_tainted][0] += (current_php+":")


    else:
        # Get the tainted variable names
        for line in vld_output:
            if line.split()[1].isdigit():
                current_php_line =  line.split()[0] 
            if "RECV" in line:
                for item in range(len(line.split())):
                    if "!" in line.split()[item]:
                        new_name = line.split()[item]
                # Translate !var to $var
                new_name = compiled_var[new_name]
                
                for recv_pos in arg_pos.keys():
                    # Add on to both dict for the tainted argument parsed
                    for keys in translation_dict.keys():
                        if arg_pos[recv_pos] in translation_dict[keys]:

                            variable_dict[keys].append(func_name + ":" + current_php_line+":")
                            translation_dict[keys].append(func_name + "_" + new_name)
                    break
                              
    php_line_tainted = False
    tainted_func = False
 

    temp_translation_dict = dict(translation_dict)
    taint_dict = dict(variable_dict)


    reverse_compile = {}
    for key in compiled_var:
        # Translate $ to !
        reverse_compile[compiled_var[key]] = key


    current_php = last_php

    vld_output = vld_output[int(user_op_line):]

        
    for line in vld_output:
        variable_dict = dict(taint_dict)
        translation_dict = dict(temp_translation_dict)
        if line.split()[1].isdigit():
                current_php =  line.split()[0] 
                php_line_tainted = False
                sink_detected = False
                saniti_detected = False
                sanitized_return = False
                temp_var_tainted = False
                tainted_func = False
                if current_php >= sink_line and sink_line != "-1":
                    break
                ### Clean var_dict of repeated entries
                for keys in variable_dict.keys():
                    for counter in range(len(variable_dict[keys])):
                        
                        taint_str = list(dict.fromkeys(variable_dict[keys][counter].split(":")))
                        
                        temp_str = taint_str
                        
                        for item in taint_str:
                            if item + "S" in taint_str and "S" not in item:
                                temp_str.remove(item)
                        variable_dict[keys][counter] = ":".join(temp_str)


        if "!" in line:     

            for taint_key in (key for key_list in translation_dict.values() for key in key_list) :
                if "$"+taint_key.split("_$")[-1] in reverse_compile.keys():
                    translated_var = reverse_compile["$"+taint_key.split("_$")[-1]]
                    
                    if taint_key.split("_$")[0] == func_name and re.search(translated_var+r"(?!\d)", line):
                        # Checks if any tainted function is found in the php line and that taint_key is pointing to the correct variable (Since variables with same name can exist in 2 different functions)
                        # Also checks if the key is not found in the sanitization list to ensure that this is a proper tainted variable
                        
                        if taint_key not in saniti_list:
                            
                            php_line_tainted = True
                            
                        
                        for element_count in range(len(taint_dict[trans_reverse_search(translation_dict, taint_key)])):
                            if taint_dict[trans_reverse_search(translation_dict, taint_key)][element_count].startswith(func_name + ":"):
                                if "S" in taint_dict[trans_reverse_search(translation_dict, taint_key)][element_count].split(":")[-2]:
                                    # Add "S" to line numbers that the variable has been sanitized
                                    taint_dict[trans_reverse_search(translation_dict, taint_key)][element_count] += (current_php + "S" + ":")
                                    
                                    
                                    if taint_key not in saniti_list:
                                        # Adds sanitiezed variable name to the list
                                        saniti_list.append(taint_key)
                                        
                                else:
                                    # for element_count in range(len(taint_dict[trans_reverse_search(translation_dict, taint_key)])):
                                    #     if func_name + ":" in taint_dict[trans_reverse_search(translation_dict, taint_key)][element_count]:
                                    taint_dict[trans_reverse_search(translation_dict, taint_key)][element_count] += (current_php + ":")
                                                            
                                    
                if ("ASSIGN" in line or "FE_FETCH" in line) and re.findall(r"!\d+,\s", line):
                    if  re.findall(r"!\d+,\s!", line):
                        assigning_var = line.split()[-1].strip(",")
                        assigned_var = compiled_var[assigning_var]
                        if (func_name + "_" + assigned_var) not in saniti_list:
                            php_line_tainted = True
                            
                        else: 
                            php_line_tainted = False
                    taint_var = line.split()[-2].strip(",")
                    translated_var = compiled_var[taint_var]
                    checker = False
                    
                    for elements in translation_dict.values():

                        if func_name + "_" + translated_var not in elements:
                            checker = True
                            
                            
                        else:
                            
                            checker = False
                            if (saniti_detected or sanitized_return or not php_line_tainted):
                                element = elements[0]
                                for counter in range(len(variable_dict[element])):
                                    if func_name + ":" in variable_dict[element][counter] and variable_dict[element][counter].startswith(func_name + ":"):
                                        taint_dict[element][counter] = taint_dict[element][counter][:-1]+ "S:"
                                        if func_name + "_" + translated_var not in saniti_list:
                                        # Adds sanitiezed variable name to the list
                                            saniti_list.append(func_name + "_" + translated_var)
                            else:

                                if taint_key == func_name + "_" + translated_var:
                                    for element_count in range(len(taint_dict[trans_reverse_search(translation_dict, taint_key)])):
                                        if taint_dict[trans_reverse_search(translation_dict, taint_key)][element_count].startswith(func_name + ":"):
                                            if "S" in taint_dict[trans_reverse_search(translation_dict, taint_key)][element_count].split(":")[-2] and (func_name + "_" + translated_var) in saniti_list:
                                    # Removes the sanitized indicator when sanitized variable has been assigned a tainted variable
                                                taint_dict[trans_reverse_search(translation_dict, taint_key)][element_count] = taint_dict[trans_reverse_search(translation_dict, taint_key)][element_count][:-2]+":"

                            break
                    

                    if checker:
                        
                        if (saniti_detected or sanitized_return or not php_line_tainted):
                                
                                #temp_translation_dict[func_name + "_" + translated_var] = [func_name + "_" + translated_var]
                                #taint_dict[func_name + "_" + translated_var] = ["class= "+ variable_class, func_name+":"+current_php+ "S" + ":"]
                                if func_name + "_" + translated_var not in saniti_list:
                                        # Adds sanitiezed variable name to the list
                                    saniti_list.append(func_name + "_" + translated_var)
                        else:
                            if "(null)_"+translated_var in global_list:
                                if "(null)_"+ translated_var not in temp_translation_dict.keys():
                                    temp_translation_dict["(null)_"+ translated_var] = [func_name + "_" + translated_var]
                                else:
                                    temp_translation_dict["(null)_"+ translated_var].append(func_name + "_" + translated_var)
                                taint_dict["(null)_" + translated_var] = [func_name+":"+current_php+":"]
                            else:
                                
                                temp_translation_dict[func_name + "_" + translated_var] = [func_name + "_" + translated_var]
                                taint_dict[func_name + "_" + translated_var] = [func_name+":"+current_php+":"]
                            
                            for element_count in range(len(taint_dict[trans_reverse_search(translation_dict, taint_key)])):
                                if taint_dict[trans_reverse_search(translation_dict, taint_key)][element_count].startswith(func_name + ":"):
                                    if "S" in taint_dict[trans_reverse_search(translation_dict, taint_key)][element_count].split(":")[-1] and (func_name + "_" + translated_var) in saniti_list:
                                # Removes the sanitized indicator when sanitized variable has been assigned a tainted variable
                                
                                        taint_dict[trans_reverse_search(translation_dict, taint_key)][-1] = taint_dict[trans_reverse_search(translation_dict, taint_key)][-1][:-1]
        # Removed because below does the job
        # for funcs in saniti_func_list:
        #     if "INIT_FCALL" in line and funcs in line:
        #         saniti_detected = True

        
        if "ECHO" in sink_func_list and php_line_tainted and "ECHO" in line:
            
            return variable_dict, translation_dict, sanitized_return, sink_detected
                
        
            

        if "SEND" in line and  line.split()[-1] in compiled_var.keys():
            if sink_detected and interfunc_stack[-1].strip("/")[-1] in sink_func_list:
                sink_line = current_php  
                return variable_dict, translation_dict, sanitized_return, sink_detected


    ######### Inter-function and class tracking ##########


        if "INIT_FCALL" in line or  "INIT_NS_FCALL" in line:
            # Name of function that is initialized, normal function call
            interfunc_name = line.split()[-1].strip("'").split("%5C")[-1]
            interfunc_stack.append(interfunc_name)
            # State if function is tainted if argument is tainted
            tainted_func = False
            if interfunc_name in saniti_func_list:
                saniti_detected = True
                

                

        if "INIT_METHOD" in line or "INIT_STATIC_METHOD" in line:
            interfunc_name = line.split()[-1].strip("'").split("%5C")[-1]
            if interfunc_name in saniti_func_list:
                saniti_detected = True

            if line.split()[-2].strip(",") in compiled_var.keys():
                for element in list(translation_dict.values()):
                    if (func_name + "_" + compiled_var[line.split()[-2].strip(",")]) in element:
                        # Checks if the argument parsed in tainted
                        arg_pos[0] = func_name + "_" + compiled_var[line.split()[-2].strip(",")]
                        tainted_func = True
                        
            interfunc_stack.append(interfunc_name)

                        
            
        if "NEW" in line:
            # Name of function that is initialized, object is initialized
            interfunc_name = line.split()[-1].replace("'","").split("%5C")[-1]
            interfunc_stack.append(interfunc_name+"__construct")
            # State if function is tainted if argument is tainted
            tainted_func = False
            variable_class = line.split()[-1].strip("'")

        

        if "SEND" in line:
            pos += 1
            if line.split()[-1] in compiled_var.keys():
                for element in list(translation_dict.values()):
                    
                    if (func_name + "_" + compiled_var[line.split()[-1]]) in element:
                        
                        # Checks if the argument parsed in tainted
                        arg_pos[pos] = func_name + "_" + compiled_var[line.split()[-1]]
                        tainted_func = True
                        for element_count in range(len(taint_dict[trans_reverse_search(translation_dict, func_name + "_" + compiled_var[line.split()[-1]])])):
                            if taint_dict[trans_reverse_search(translation_dict, func_name + "_" + compiled_var[line.split()[-1]])][element_count].startswith(func_name + ":"):
                                taint_dict[trans_reverse_search(translation_dict, func_name + "_" + compiled_var[line.split()[-1]])][element_count] += (current_php + ":")
                                taint_dict[trans_reverse_search(translation_dict, func_name + "_" + compiled_var[line.split()[-1]])][element_count] = taint_dict[trans_reverse_search(translation_dict, func_name + "_" + compiled_var[line.split()[-1]])][element_count][:-1] # strip last comma
                                taint_dict[trans_reverse_search(translation_dict, func_name + "_" + compiled_var[line.split()[-1]])][element_count] += "F" + interfunc_name + ":"
                        

            
        if ("DO_ICALL" in line or "DO_FCALL" in line):

            if len(interfunc_stack) > 0:

                interfunc_name = interfunc_stack.pop()

            
            
            
            if interfunc_name in sink_func_list and tainted_func:
                return variable_dict, translation_dict, sanitized_return, sink_detected
            if (tainted_func) and interfunc_name in func_list[filename].keys():

                
                if interfunc_name in sink_func_list and tainted_func:
                    return variable_dict, translation_dict, sanitized_return, sink_detected
                if (tainted_func) and interfunc_name in func_list[filename].keys():
                    
                    # Checks if function called is submitted by user, otherwise ignore since no info
                    # for element_count in range(len(taint_dict[trans_reverse_search(translation_dict, taint_key)])):
                    #     if taint_dict[trans_reverse_search(translation_dict, taint_key)][element_count].startswith(func_name + ":"):
                    #         print("1:",taint_dict[trans_reverse_search(translation_dict, taint_key)])
                    #         taint_dict[trans_reverse_search(translation_dict, taint_key)][element_count] = taint_dict[trans_reverse_search(translation_dict, taint_key)][element_count][:-1] # strip last comma
                    #         taint_dict[trans_reverse_search(translation_dict, taint_key)][element_count] += "F" + interfunc_name + ":"
                    
                    if interfunc_name not in saniti_func_list:
                        dest_php = func_to_php[interfunc_name]
                        
                        taint_dict, temp_translation_dict, sanitized_return, sink_detected = funcsecurity(
                            func_list, linked, func_to_php,
                            vld_output = func_list[dest_php][interfunc_name], 
                            compiled_var = linked[dest_php][interfunc_name], 
                            sink_func_list = sink_func_list, 
                            saniti_func_list = saniti_func_list,
                            variable_dict = variable_dict, 
                            translation_dict = translation_dict, 
                            func_name = interfunc_name, 
                            arg_pos = arg_pos, 
                            interfunc = True, 
                            filename = dest_php)
                        
                        if sink_detected:
                            return variable_dict, translation_dict, sanitized_return, sink_detected
                            
                        pos = 0
                        ### vld stores temporary values that are being parsed between function in $.
                        if "$" in line:
                            temp_var_tainted = not sanitized_return
                    else:
                        sanitized_return = True

        if "RETURN" in line and not php_line_tainted and "null" not in line and clean_return == "0":
            clean_return = True
            
        elif "RETURN" in line and php_line_tainted and "null" not in line:
            clean_return = False
            
    ### Global Variable Tracking ###
        if "BIND_GLOBAL" in line:
            global_var = "$" + line.split(",")[-1].replace("'","").replace(" ","")
            global_list.append("(null)_" + global_var) 
        if "FETCH" in line and "global" in line:
            global_detected = True
        if "FETCH" in line and "global" not in line and global_detected:
            global_var = "$" + line.split(",")[-1].replace("'","")
            global_list.append("(null)_" + global_var) 


        


    func_dict = {}
    argument_list = []

    # Checks if a function calls for a tainted variable as an argument

    tainted_func = False
    pos = 0




    
    return variable_dict, translation_dict, sanitized_return, sink_detected

# Find and store compiled variables in dictionary
def get_variable(vld_handle, func_list, linked, func_to_php, line_number = None):
    # Line number is for retrieving function name from Line number of user input
    
    pattern = r"compiled vars:\s*(.*?)(?=\n|$)"
    compiled_pattern = re.compile(pattern)

    op_pattern = r"-{85,}([\s\S]*?)RETURN\s*[nul1]+\n\n"
    compiled_op_patten = re.compile(op_pattern)

    func_name_pattern = r"(function name\: .+[^\n]|Class .+[^\n]|End of class .+[^\n])"
    #func_name_pattern = r"(function name\: .+[^\n])"
    compiled_name_pattern = re.compile(func_name_pattern)


    with open(vld_handle, "r") as file:
        vld_output = file.read()

    compiled_var = re.findall(compiled_pattern, vld_output)

    op_codes = re.findall(compiled_op_patten, vld_output)

    func_names = re.findall(compiled_name_pattern, vld_output)


    count = 0
    php_handle = vld_handle.replace(".txt",".php")
    class_name = ""
    function_found = False
    user_function = ""
    linked[php_handle] = {}
    func_list[php_handle] = {}

    for names in range(len(func_names)):
        
        if "function name:" in func_names[names]:
            final = {}
            if compiled_var[count] == "none":
                final["none"] = "none"
            else:
                
                vars = compiled_var[count].split(", ")
                for sets in vars:
                    final[sets.split(" = ")[0]] = sets.split(" = ")[1]
            replaced_name = func_names[names].split("\\")[-1].split("function name:  ")[-1]
            
            if "__construct" in replaced_name:
                replaced_name =  f"{class_name}.{replaced_name}"
            elif replaced_name == "(null)":
                replaced_name = helper.get_self_filename(php_handle, with_path=True)
            if class_name != "":
                replaced_name = f"{class_name}.{replaced_name}"
                # replaced_name = f"{replaced_name}"


            linked[php_handle][replaced_name] = final
            func_list[php_handle][replaced_name] = op_codes[count].split("\n")[1:]
            if "(null)" not in  replaced_name:
                func_to_php[replaced_name] = php_handle
            
            if not function_found and line_number != None:
                op_code_list = op_codes[count].split("\n")
               
                for line in op_code_list:
                    if len(line) > 0 and line.split()[1].isdigit():
                        if line.split()[0] == str(line_number):
                            
                            user_function = replaced_name
                            function_found = True

            count += 1
        elif "End of Class" in func_names[names]:
            class_name = ""
        else:
            class_name = func_names[names].split()[-1].strip(":")
    return func_list, linked, func_to_php, user_function

        


def trans_reverse_search(trans_dict, trans_value):
    # Reverse the look up of trans_dict (Get key with value)
    for key in trans_dict:
        if trans_value in trans_dict[key]:
            return key
    return None

##### WORK IN PROGRESS #####

def getUseFiles(php_handle, func_list, linked, func_to_php):
    # Checks for imports from via use

    current_path = php_handle.split("/")
    namespace_pattern = r"namespace \s+[^\;]+"
    namespace_compile = re.compile(namespace_pattern)
    import_pattern = r"[^\s]*use\s+[^\;]+|[^\s]*require_once\s+[^\;]+|[^\s]*require\s+[^\;]+|[^\s]*include\s+[^\;]+|[^\s]*include_once\s+[^\;]+"
    import_compile = re.compile(import_pattern)


    with open(php_handle, "r") as file:
            vld_output = file.read()

    namespace_list = re.findall(namespace_compile, vld_output)
    import_list = re.findall(import_compile, vld_output)

    # if namespace_list:
    #     namespace = namespace_list.split()[-1]
    # else:
    #     namespace = ""    
       
    for line in import_list:
        line = line.replace("'","").strip(";")
        
        if "use " in line:
            func_list, linked, func_to_php, user_function = import_file(get_next_directory(current_path,line.split("use ")[1], namespace = True), func_list, linked, func_to_php)
        elif "require_once " in line:
            func_list, linked, func_to_php, user_function = import_file(get_next_directory(current_path,line.split("require_once ")[1]), func_list, linked, func_to_php)
        elif "require " in line:
            func_list, linked, func_to_php, user_function = import_file(get_next_directory(current_path,line.split("require ")[1]), func_list, linked, func_to_php)
        elif "include_once " in line:
            func_list, linked, func_to_php, user_function = import_file(get_next_directory(current_path,line.split("include_once ")[1]), func_list, linked, func_to_php)
        elif "include " in line:
            func_list, linked, func_to_php, user_function = import_file(get_next_directory(current_path,line.split("include ")[1]), func_list, linked, func_to_php)
    return func_list, linked, func_to_php
            
        
def get_next_directory(current_path, next_path, namespace = False):
    # Returns the relative path to user uploads of the destination file
    if namespace:
        # Use statement use some weird thing called namespace, have to account for it here
        next_path = os.path.join(USER_UPLOAD, next_path).replace("\\","/")
        
    else:
        # Relative Path
        next_path = next_path.split("/")
        current_path.pop(-1)
        for directory in next_path:
            if ".." in directory:
                current_path.pop(-1)
                
            else:
                current_path.append(directory)
        
        next_path = "/".join(current_path)
        
    next_path = next_path.replace("\\", "/")
    if ".php" not in next_path:
        # For the use statements
        next_path += ".php"
    
    return next_path


    
    
def get_vld(php_handle):
    # Check if the original php is in the submitte folder
    # if does not exists, return 0
    # Check if vld-output has been generated, if havent then generate
    php_filename = os.path.splitext(php_handle)[0]
    vld_handle = php_filename + ".txt"
    if not os.path.isfile(vld_handle):
        vld_command = "php -d vld.active=1 -d vld.execute=0 {php_file} > {vld_txt} 2>&1".format(php_file = php_handle, vld_txt = vld_handle)
        os.system(vld_command)
    return vld_handle

def import_file(php_handle,  func_list, linked, func_to_php, line_number = None,):
    # Basic checks file imported for importing external files, vld_output and opcodes
    user_function = ""
    if os.path.isfile(php_handle):
        func_list, linked, func_to_php = getUseFiles(php_handle, func_list, linked, func_to_php)
        vld_handle = get_vld(php_handle)
        func_list, linked, func_to_php, user_function = get_variable(vld_handle, func_list, linked, func_to_php, line_number)
   
    return func_list, linked, func_to_php, user_function


### User defined variables ###
def funcsecurity_prepare(user_tainted,line_number,sink_func_list,saniti_func_list,user_directory,function_name=None, func_list = None, linked = None, func_to_php = None):
    start_php_directory = user_directory
    if func_list == None:
        func_list = {}
    if linked == None:
        linked = {}
    if func_to_php == None:
        func_to_php = {}

        
    if function_name == None:
        func_list, linked, func_to_php, function_name = import_file(start_php_directory, line_number, func_list, linked, func_to_php)
    else:
        func_list, linked, func_to_php, temp = import_file(start_php_directory, func_list, linked, func_to_php)
    if function_name == "":
        raise VariableNotFound("Function Name cannot be resolved")
    # When user inputs global as function_name, it refers to the function (null)
    v, t, s, sd = funcsecurity(func_list, linked, func_to_php,
                    vld_output = func_list[start_php_directory][function_name], 
                    compiled_var = linked[start_php_directory][function_name], 
                    user_tainted = user_tainted, 
                    line_number = line_number, 
                    func_name = function_name,
                    sink_func_list = sink_func_list,
                    saniti_func_list = saniti_func_list,
                    filename = start_php_directory
                    )
    
    return v, t

def interfunction_superglobal(interfunc_name, sink_func_list, variable_dict, translation_dict, arg_pos, start_php_directory, func_list, linked, func_to_php):
    #start_php_directory = start_php_directory + "/" + start_php_directory.split("/")[-1] #+ ".php"
    
    func_list, linked, func_to_php, user_function = import_file(start_php_directory, func_list, linked, func_to_php)

    # Check if function exists (if no, assume to be a library function)
    if interfunc_name not in func_to_php.keys():
        return {}, None
    
    dest_php = func_to_php[interfunc_name]
   

    taint_dict, temp_translation_dict, sanitized_return, sink_detected = funcsecurity(
                        func_list, linked, func_to_php,        
                        vld_output=func_list[dest_php][interfunc_name], 
                        compiled_var=linked[dest_php][interfunc_name], 
                        sink_func_list = sink_func_list, 
                        variable_dict = variable_dict, 
                        translation_dict = translation_dict, 
                        func_name = interfunc_name, 
                        arg_pos = arg_pos, 
                        interfunc = True, 
                        filename = dest_php)
    
    return taint_dict, sanitized_return


def superglobal_getter(var_name, sink_func_list, saniti_func_list, user_directory, source_line = 0):
    # Finds for $_GET, $_POST or $_REQUEST in ALL user directory
    # var_name indicates which to find

    if source_line == "":
        source_line = 0

    func_list = {}
    linked = {}
    ### Create dictionary to indicate function name (key) is in which php file (value)
    func_to_php = {}

    # var_dict for each file
    final_J_data = {}

    func_name_pattern = r"function name\: .+[^\n]"
    class_start_pattern =r"Class .+[^\n]"
    class_end_pattern = r"End of class .+[^\n]"
    function_pattern = r"function\s\S+\("
    compiled_pattern = r"compiled vars:\s*(.*?)(?=\n|$)"
    

    func_name_compile = re.compile(func_name_pattern)
    class_start_compile = re.compile(class_start_pattern)
    class_end_compile = re.compile(class_end_pattern)
    function_compile = re.compile(function_pattern)
    compiled_compile = re.compile(compiled_pattern)
    
    function_name = ""
    class_name = ""
    pos = 0
    final = {}
    temp_dict = {}
    interfunc_stack = []
    arg_pos = {}
    sanitized_return = False
    general_superglobal_arg = ""
    user_source_func = False
    source_function_detected = False

    if "$_" in var_name and "[" in var_name:
        superglobal_name = var_name.split("[")[0].strip("$")
        superglobal_arg = var_name.split("[")[1].strip("]").replace("\"","'")
    elif "()" in var_name:
        # Used for Source Functions. superglobal_name is name of function
        superglobal_name = var_name.replace("()", "")
        superglobal_arg = "None"
        user_source_func = True

    elif "$_" in var_name:
        superglobal_name = var_name.strip("$")
        superglobal_arg = "None"
    else:
        raise VariableNotFound("Invalid Source Variable / Function")
    if ".php" in user_directory:
        php_files = [user_directory]
    else:
        upload_path = pathlib.Path(user_directory)
        php_files = list(upload_path.rglob("*.php"))
    for file_name in php_files:
        file_name = str(file_name)
        vld_handle = get_vld(file_name)
        shorten_file_name = helper.get_self_filename(vld_handle, with_path=True)
        final_J_data[shorten_file_name] = []
        with open(vld_handle, "r") as file:
            vld_output = file.readlines()
        for line in vld_output:

            if len(line.split()) > 1 and line.split()[1].isdigit():
                current_php =  line.split()[0]
                var_detected = False
                superglobal_detected = False
                sanitized_return = False
                source_function_detected = False
                if len(temp_dict) > 0:
                    final_J_data[shorten_file_name].append(temp_dict)
                temp_dict = {}
            
            if re.findall(class_start_compile, line):
                class_name = line.split()[-1].strip(":")
            if re.findall(class_end_compile, line):
                class_name = "" 
            if re.findall(func_name_compile, line):
                function_name = line.split("\\")[-1].split("function name:  ")[-1].replace("\n","")
                if function_name == "__construct":
                    function_name = f"{class_name}.{function_name}"
                if function_name == "(null)":     # Check function is page global scope (code not nested within a function)
                    function_name = shorten_file_name
                if class_name != "":
                    function_name = f"{class_name}.{function_name}"

            if re.findall(compiled_compile, line):
                compile_line = line.strip("compiled vars:  ").split(",")
                for sets in compile_line:
                    if "none\n" not in sets:
                        final[sets.split(" = ")[0].replace(" ","")] = sets.split(" = ")[1].replace("\n","")
            
            if "INIT_FCALL" in line or  "INIT_NS_FCALL" in line:
                # Name of function that is initialized, normal function call
                interfunc_name = line.split()[-1].strip("'").split("%5C")[-1]
                interfunc_stack.append(interfunc_name)
                # State if function is tainted if argument is tainted
                tainted_func = False
                sanitized_return = False
                if interfunc_name in saniti_func_list:
                    saniti_detected = True
                if interfunc_name == superglobal_name and (source_line == current_php or source_line == 0):
                    temp_dict["(null)" + "_$" + superglobal_name + "_" + general_superglobal_arg] = [function_name+":"+current_php+":"]   
                     

                

            if "INIT_METHOD" in line or "INIT_STATIC_METHOD" in line:
                interfunc_name = line.split()[-1].strip("'").split("%5C")[-1]
                method_init = True
                if interfunc_name in saniti_func_list:
                    saniti_detected = True
                interfunc_stack.append(interfunc_name)
                if interfunc_name == superglobal_name and (source_line == current_php or source_line == 0):
                    temp_dict["(null)" + "_$" + superglobal_name + "_" + general_superglobal_arg] = [function_name+":"+current_php+":"]   



            if ((("FETCH_R" in line or "FETCH_FUNC_ARG" in line) and "global" in line ) or "FETCH_IS" in line) and superglobal_name in line:
                superglobal_detected = True
                if superglobal_arg == "None" and (source_line == current_php or source_line == 0):
                    general_superglobal_arg = line.split()[-1].replace("'","")
                    temp_dict["(null)" + "_$" + superglobal_name + "_" + general_superglobal_arg] = [function_name+":"+current_php+":"]    
                    if len(interfunc_stack) == 0:
                        final_J_data[shorten_file_name].append(temp_dict)



                
            if ("FETCH_DIM_R" in line or "FETCH_DIM_FUNC_ARG" in line or "ISSET_ISEMPTY_DIM_OBJ" in line) and (superglobal_arg in line or superglobal_arg == "None") and superglobal_detected: 
                var_detected = True  
                
                if (source_line == current_php or source_line == 0):
                    if superglobal_arg == "None":
                        # For when user does not provide a name in the [] for the superglobal
                        general_superglobal_arg = line.split()[-1].replace("'","")
                        temp_dict["(null)" + "_$" + superglobal_name + "_" + general_superglobal_arg] = [function_name+":"+current_php+":"]    
                        
                    else:
                        general_superglobal_arg = superglobal_arg
                        temp_dict["(null)" + "_$" + superglobal_name + "_" + general_superglobal_arg] = [function_name+":"+current_php+":"]  

            
            
            if "SEND" in line:
                
                pos += 1
                if (var_detected or superglobal_arg == "None") and superglobal_detected:
                    
                    arg_pos[pos] = "(null)" + "_$" + superglobal_name + "_" + general_superglobal_arg
                    tainted_func = True
                    
            
            if ("DO_ICALL" in line or "DO_FCALL" in line):
                if len(interfunc_stack) > 0:
                    interfunc_name = interfunc_stack.pop()
                    if (((var_detected or superglobal_arg == "None") and superglobal_detected  and tainted_func) or (interfunc_name == superglobal_name and user_source_func)) and (source_line == current_php or source_line == 0):
                        # Checks if function call has tainted superglobal or it is calling a source function
                        translation_dict = {}
                        translation_dict["(null)" + "_$" + superglobal_name + "_" + general_superglobal_arg] = ["(null)" + "_$" + superglobal_name + "_" + general_superglobal_arg]
                        temp_dict["(null)" + "_$" + superglobal_name + "_" + general_superglobal_arg][0] = temp_dict["(null)" + "_$" + superglobal_name + "_" + general_superglobal_arg][0][:-1]
                        temp_dict["(null)" + "_$" + superglobal_name + "_" + general_superglobal_arg][0] += "F" + interfunc_name + ":"
                        if interfunc_name not in saniti_func_list:
                            v, sanitized_return = interfunction_superglobal(interfunc_name, sink_func_list, temp_dict, translation_dict, arg_pos, file_name, func_list, linked, func_to_php)
                            temp_dict.update(v)
                            final_J_data[shorten_file_name].append(temp_dict)
                            if len(interfunc_stack) == 0:
                                temp_dict = {}
                        else:
                            sanitized_return = True
                        if user_source_func:
                            source_function_detected = True
                    pos = 0


            if "ASSIGN" in line and (superglobal_detected or source_function_detected) and "!" in line:
                if (var_detected or superglobal_arg == "None") and not sanitized_return and (source_line == current_php or source_line == 0):
                    
                    assigning_var = "!" + line.split("!")[1].split(",")[0].replace("\n","")
                    assigning_var = final[assigning_var]
                    v,t = funcsecurity_prepare(assigning_var, current_php, sink_func_list, saniti_func_list, file_name, function_name=function_name, func_list = func_list, linked = linked, func_to_php = func_to_php)
                    temp_dict.update(v)
                    final_J_data[shorten_file_name].append(temp_dict)
                    temp_dict = {}
                    superglobal_detected = False
                    source_function_detected = False



    # Converting python structure to JSON.
    json_data = json.dumps(final_J_data, indent=2)


    # Opens a file with a respective name and write contents of json dump
    return final_J_data
