import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
import pandas as pd
from deap import base, creator, tools, algorithms
import random
import numpy as np
import warnings

warnings.filterwarnings('ignore')

class Schedule:
    def __init__(self, hardConstraintPenalty, data= None):
        self.hardConstraintPenalty = hardConstraintPenalty
        self.intakes = ['Jan', 'Mar', 'Jun', 'Aug', 'Oct']
        self.programme = ['SE', 'DSBA']
        self.modules = ['MSDP', 'RM', 'OOSSE', 'SESE', 'SQE', 'ST', 'IA', 'NDP', 'RMCE | RMCP', 'BDAT', 'DM', 'MDA | NLP', 
                       'BIS', 'AML', 'MMDA', 'DAP', 'ABAV', 'BSSMMA | CIS', 'TSF | DL', 'SEM | DPM', 'ORO | BIA']
        self.slot_intake = 4
        
        # Load both SE and DSBA student data
        self.SE_students_data = self.load_SE_student_data(data) if data is not None else None
        self.DSBA_students_data = self.load_DSBA_student_data(data) if data is not None else None
        
        # Process both SE and DSBA student data
        if self.SE_students_data is not None:
            self.SE_incomplete_modules, self.SE_completed_modules = self.process_SE_student_data()
        if self.DSBA_students_data is not None:
            self.DSBA_incomplete_modules, self.DSBA_completed_modules = self.process_DSBA_student_data()
                  
    def __len__(self):
        return len(self.intakes) * self.slot_intake * len(self.programme)
    
    def getIntakeSchedule(self, schedule):
        programme_schedule = {programme: {intake: [] for intake in self.intakes} for programme in self.programme}
        index = 0

        for programme in self.programme:
            for intake in self.intakes:
                for _ in range(self.slot_intake):
                    if index < len(schedule):
                        module = self.modules[schedule[index]]
                        programme_schedule[programme][intake].append(module)
                        index += 1
        return programme_schedule
    
    def load_SE_student_data(self, data):
        SE_students_data = data[data['COURSE_DESCRIPTION'] != 'MSc in Data Science and Business Analytics']
        SE_students_data = SE_students_data.drop(["INTAKE_CODE", "MODULE_CODE", "STUDY_MODE"], axis=1)
        module_name_changes = {
            'Managing Software Development Projects': 'MSDP',
            'Reliability Management': 'RM',
            'Object-Oriented Software Systems Engineering': 'OOSSE',
            'Object Oriented Software Systems Engineering': 'OOSSE',
            'Software Engineering Support Environments': 'SESE',
            'Software Quality Engineering': 'SQE',
            'Security Technologies': 'ST',
            'Research Methodology in Computing and Engineering': 'RMCE | RMCP',
            'Big Data Analytics and Technologies': 'BDAT',
            'Data Management': 'DM',
            'Internet Applications': 'IA',
            'Natural Language Processing': 'MDA | NLP',
            'Network Design and Performance': 'NDP'
        }
        SE_students_data['MODULE_NAME'] = SE_students_data['MODULE_NAME'].replace(module_name_changes)
        valid_modules = ['MSDP', 'RM', 'OOSSE', 'SESE', 'SQE', 'ST', 'RMCE | RMCP', 'BDAT', 'DM', 'IA', 'MDA | NLP', 'NDP']
        SE_students_data = SE_students_data[SE_students_data['MODULE_NAME'].isin(valid_modules)]

        # Handle duplicates
        duplicated_modules = SE_students_data[SE_students_data.duplicated(['STUDENT_NUMBER', 'MODULE_NAME'], keep=False)]
        def filter_grades(group):
            if group['GRADE'].notna().sum() > 0:
                return group[group['GRADE'].notna()].drop_duplicates(subset=['STUDENT_NUMBER', 'MODULE_NAME'], keep='first')
            else:
                return group.drop_duplicates(subset=['STUDENT_NUMBER', 'MODULE_NAME'], keep='first')

        # Apply the filter_grades function
        filtered_students = duplicated_modules.groupby(['STUDENT_NUMBER', 'MODULE_NAME']).apply(filter_grades).reset_index(drop=True)
        SE_students_data = pd.concat([SE_students_data.drop(index=duplicated_modules.index), filtered_students])
        SE_students_data.reset_index(drop=True, inplace=True)
        
        return SE_students_data
    
    def process_SE_student_data(self):
        SE_each_student_info = self.SE_students_data.groupby('STUDENT_NUMBER').apply(
            lambda x: {'Modules': x['MODULE_NAME'].tolist(), 'Grades': x['GRADE'].tolist()}
        ).to_dict()
        
        incomplete_modules = {}
        completed_modules = {}

        for student_id, modules_info in SE_each_student_info.items():
            modules = modules_info['Modules']
            grades = modules_info['Grades']

            incomplete_modules[student_id] = []
            completed_modules[student_id] = []

            for module, grade in zip(modules, grades):
                if pd.isna(grade) or grade in ["", "N/A"]:
                    incomplete_modules[student_id].append(module)
                else:
                    completed_modules[student_id].append(module)
        
        # Handle elective modules
        elective = ["BDAT", "DM", "IA", "MDA | NLP", "NDP"]
        for student_id, completed_modules_info in completed_modules.items():
            completed_elective = set(completed_modules_info) & set(elective)

            if len(completed_elective) >= 3:
                for student_id, incomplete_modules_info in incomplete_modules.items():
                    extra_elective = set(incomplete_modules_info) & set(elective)
                    
                    for module in extra_elective:
                        completed_modules[student_id].append(module)
                        incomplete_modules_info.remove(module)
        
        return incomplete_modules, completed_modules
    
    def calculate_SE_student_violations(self, programme_schedule):
        total_violations = 0
        se_schedule = programme_schedule['SE']
        student_suggestions = {}
        student_violations = {}

        for student_id, incomplete_modules_info in self.SE_incomplete_modules.items():
            # Initialize student suggestions with "-" for each intake
            student_suggestions[student_id] = ['-'] * len(self.intakes)
            student_violations[student_id] = 0
            
            # Make a copy of incomplete modules list
            incomplete_modules_list = incomplete_modules_info.copy()
            
            # Store initial length of incomplete modules
            initial_modules_count = len(incomplete_modules_info)
            
            # If no incomplete modules, continue with all "-" and no violations
            if not incomplete_modules_list:
                continue

            rmce_assigned = False
            violations = 0
            
            # Process each intake
            for i, (intake, intake_modules_info) in enumerate(se_schedule.items()):
                # If no more modules to assign, stop checking for violations
                if not incomplete_modules_list:
                    break
                    
                # Prioritize to assign RMCE | RMCP if not yet assigned
                if not rmce_assigned and 'RMCE | RMCP' in incomplete_modules_list and 'RMCE | RMCP' in intake_modules_info:
                    student_suggestions[student_id][i] = 'RMCE | RMCP'
                    incomplete_modules_list.remove('RMCE | RMCP')
                    rmce_assigned = True
                    continue
                
                # Assign for other modules
                module_assigned = False
                for module in incomplete_modules_list[:]:
                    if module in intake_modules_info:
                        student_suggestions[student_id][i] = module
                        incomplete_modules_list.remove(module)
                        module_assigned = True
                        break
                
                # Only count a violation if couldn't assign a module and still have modules to assign
                if not module_assigned and incomplete_modules_list:
                    violations += 1
            # Add violations for remaining modules if initial count was ≤ 5
            if initial_modules_count <= 5 and incomplete_modules_list:
                violations += len(incomplete_modules_list)
            
            # If RMCE | RMCP is assigned, reduce violations by 1
            if 'RMCE | RMCP' in student_suggestions[student_id]:
                violations = max(0, violations - 1)
            # Or if RMCE | RMCP is already completed, reduce violations by 1
            elif (student_id in self.SE_completed_modules and 
                'RMCE | RMCP' in self.SE_completed_modules[student_id]):
                violations = max(0, violations - 1)
            
            student_violations[student_id] = violations
            total_violations += violations

        return total_violations, student_suggestions, student_violations

    def load_DSBA_student_data(self, data):
        DSBA_students_data = data[data['COURSE_DESCRIPTION'] != 'MSc in Software Engineering']
        DSBA_students_data = DSBA_students_data.drop(["INTAKE_CODE", "MODULE_CODE", "STUDY_MODE"], axis=1)

        module_name_changes = {
            'Big Data Analytics and Technologies': 'BDAT',
            'Data Management': 'DM',
            'Business Intelligence Systems': 'BIS',
            'Applied Machine Learning': 'AML',
            'Applied Machine Learning ': 'AML', # extra spacing
            'Research Methods for Capstone Project': 'RMCP',
            'Research Methodology for Capstone Project': 'RMCP',
            'Research Methodology in Computing and Engineering': 'RMCP',
            'Research Methodology': 'RMCP',
            'Research Methods for Capstone Project': 'RMCP',
            'Multivariate Methods for Data Analysis': 'MMDA',
            'Data Analytical Programming': 'DAP',
            'Advanced Business Analytics and Visualization': 'ABAV',
            'Advanced Business Analytics and Visualisation': 'ABAV',
            'Behavioural Science, Social Media and Marketing Analytics': 'BSSMMA',
            'Behavioural Science,Social Media and Marketing Analytics': 'BSSMMA',
            'Cloud Infrastructure and Services': 'CIS',
            'Time Series Analysis and Forecasting': 'TSF',
            'Time Series Analysis and Forecasting ': 'TSF', # extra spacing
            'Deep Learning': 'DL',
            'Multilevel Data Analysis': 'MDA',
            'Natural Language Processing': 'NLP',
            'Strategies in Emerging Markets': 'SEM',
            'Data Protection and Management': 'DPM',
            'Operational Research and Optimisation': 'ORO',
            'Operational Research Optimisation': 'ORO',
            'Building IoT Applications': 'BIA'
        }

        DSBA_students_data['MODULE_NAME'] = DSBA_students_data['MODULE_NAME'].replace(module_name_changes)
        valid_modules = ['BDAT', 'DM', 'BIS', 'AML', 'RMCP', 'MMDA', 'DAP', 'ABAV', 'BSSMMA', 'CIS',
                        'TSF', 'DL', 'MDA', 'NLP', 'SEM', 'DPM', 'ORO', 'BIA']
        DSBA_students_data = DSBA_students_data[DSBA_students_data['MODULE_NAME'].isin(valid_modules)]
        
        duplicated_modules = DSBA_students_data[DSBA_students_data.duplicated(['STUDENT_NUMBER', 'MODULE_NAME'], keep=False)]

        # Handle duplicates
        def filter_grades(group):
            if group['GRADE'].notna().sum() > 0:
                return group[group['GRADE'].notna()].drop_duplicates(subset=['STUDENT_NUMBER', 'MODULE_NAME'], keep='first')
            else:
                return group.drop_duplicates(subset=['STUDENT_NUMBER', 'MODULE_NAME'], keep='first')

        # Apply the filter_grade function
        filtered_students = duplicated_modules.groupby(['STUDENT_NUMBER', 'MODULE_NAME']).apply(filter_grades).reset_index(drop=True)
        DSBA_students_data = pd.concat([DSBA_students_data.drop(index=duplicated_modules.index), filtered_students])

        # Handle DSBA special cases
        DSBA_students_data = self.handle_DSBA_special_cases(DSBA_students_data)

        # Final module name changes
        final_module_changes = {
            'RMCP': 'RMCE | RMCP',
            'NLP': 'MDA | NLP',
            'MDA': 'MDA | NLP',
            'BSSMMA': 'BSSMMA | CIS',
            'CIS': 'BSSMMA | CIS',
            'TSF': 'TSF | DL',
            'DL': 'TSF | DL',
            'SEM': 'SEM | DPM',
            'DPM': 'SEM | DPM',
            'ORO': 'ORO | BIA',
            'BIA': 'ORO | BIA'
        }
        DSBA_students_data['MODULE_NAME'] = DSBA_students_data['MODULE_NAME'].replace(final_module_changes)
        
        return DSBA_students_data

    def handle_DSBA_special_cases(self, df):
        # Function to check if student has specific modules
        def has_modules(group, module_set):
            return module_set.issubset(group['MODULE_NAME'].unique())
        
        # Handle BSSMMA, TSF, CIS case
        students_with_all = df.groupby('STUDENT_NUMBER').filter(lambda x: has_modules(x, {"BSSMMA", "TSF", "CIS"}))
        rows_to_drop = (df['STUDENT_NUMBER'].isin(students_with_all['STUDENT_NUMBER'].unique())) & (df['MODULE_NAME'] == 'CIS')
        df = df[~rows_to_drop]

        # Handle BSSMMA, TSF, DL case
        students_with_all = df.groupby('STUDENT_NUMBER').filter(lambda x: has_modules(x, {"BSSMMA", "TSF", "DL"}))
        rows_to_drop = (df['STUDENT_NUMBER'].isin(students_with_all['STUDENT_NUMBER'].unique())) & (df['MODULE_NAME'] == 'DL')
        df = df[~rows_to_drop]

        # Handle TSF, CIS, DL case
        students_with_all = df.groupby('STUDENT_NUMBER').filter(lambda x: has_modules(x, {"TSF", "CIS", "DL"}))
        rows_to_drop = (df['STUDENT_NUMBER'].isin(students_with_all['STUDENT_NUMBER'].unique())) & (df['MODULE_NAME'] == 'TSF')
        df = df[~rows_to_drop]

        # Handle BSSMMA, CIS, DL case
        students_with_all = df.groupby('STUDENT_NUMBER').filter(lambda x: has_modules(x, {"BSSMMA", "CIS", "DL"}))
        rows_to_drop = (df['STUDENT_NUMBER'].isin(students_with_all['STUDENT_NUMBER'].unique())) & (df['MODULE_NAME'] == 'BSSMMA')
        df = df[~rows_to_drop]

        # Filter out non BI pathway modules
        df = df.groupby('STUDENT_NUMBER', group_keys=False).apply(
            lambda group: group[~group['MODULE_NAME'].isin({"NLP", "DPM", "BIA"})] 
            if {"BSSMMA", "TSF"}.issubset(group['MODULE_NAME'].unique()) 
            else group
        )
        
        # Filter out non DE pathway modules
        df = df.groupby('STUDENT_NUMBER', group_keys=False).apply(
            lambda group: group[~group['MODULE_NAME'].isin({"MDA", "SEM", "ORO"})] 
            if {"CIS", "DL"}.issubset(group['MODULE_NAME'].unique()) 
            else group
        )

        return df

    def process_DSBA_student_data(self):
        DSBA_each_student_info = self.DSBA_students_data.groupby('STUDENT_NUMBER').apply(
            lambda x: {'Modules': x['MODULE_NAME'].tolist(), 'Grades': x['GRADE'].tolist()}
        ).to_dict()
        
        incomplete_modules = {}
        completed_modules = {}

        for student_id, modules_info in DSBA_each_student_info.items():
            modules = modules_info['Modules']
            grades = modules_info['Grades']

            incomplete_modules[student_id] = []
            completed_modules[student_id] = []

            for module, grade in zip(modules, grades):
                if pd.isna(grade) or grade in ["", "N/A"]:
                    incomplete_modules[student_id].append(module)
                else:
                    completed_modules[student_id].append(module)

        # Handle electives
        elective = ["MDA | NLP", "SEM | DPM", "ORO | BIA"]
        for student_id in completed_modules:
            completed_elective = set(completed_modules[student_id]) & set(elective)
            if len(completed_elective) >= 1:
                for student_id, incomplete_modules_info in incomplete_modules.items():
                    extra_elective = set(incomplete_modules_info) & set(elective)
                    for module in extra_elective:
                        completed_modules[student_id].append(module)
                        incomplete_modules_info.remove(module)

        return incomplete_modules, completed_modules

    def calculate_DSBA_student_violations(self, programme_schedule):
        total_violations = 0
        dsba_schedule = programme_schedule['DSBA']
        student_suggestions = {}
        student_violations = {}

        for student_id, incomplete_modules_info in self.DSBA_incomplete_modules.items():
            # Initialize student suggestions with "-" for each intake
            student_suggestions[student_id] = ['-'] * len(self.intakes)
            student_violations[student_id] = 0
            
            # Make a copy of incomplete modules list
            incomplete_modules_list = incomplete_modules_info.copy()
            
            # Store initial length of incomplete modules
            initial_modules_count = len(incomplete_modules_info)
            
            # If no incomplete modules, continue with all "-" and no violations
            if not incomplete_modules_list:
                continue

            rmce_assigned = False
            violations = 0

            # Process each intake
            for i, (intake, intake_modules_info) in enumerate(dsba_schedule.items()):
                # If no more modules to assign, stop checking for violations
                if not incomplete_modules_list:
                    break
                    
                # Prioritize to assign RMCE | RMCP if not yet assigned
                if not rmce_assigned and 'RMCE | RMCP' in incomplete_modules_list and 'RMCE | RMCP' in intake_modules_info:
                    student_suggestions[student_id][i] = 'RMCE | RMCP'
                    incomplete_modules_list.remove('RMCE | RMCP')
                    rmce_assigned = True
                    continue
                
                # Assign for other modules
                module_assigned = False
                for module in incomplete_modules_list[:]:
                    if module in intake_modules_info:
                        student_suggestions[student_id][i] = module
                        incomplete_modules_list.remove(module)
                        module_assigned = True
                        break
                    
                # Only count a violation if couldn't assign a module and still have modules to assign
                if not module_assigned and incomplete_modules_list:
                    violations += 1
            # Add violations for remaining modules if initial count was ≤ 5
            if initial_modules_count <= 5 and incomplete_modules_list:
                violations += len(incomplete_modules_list)
            
            # If RMCE | RMCP is assigned, reduce violations by 2
            if 'RMCE | RMCP' in student_suggestions[student_id]:
                violations = max(0, violations - 2)
            # Or if RMCE | RMCP is already completed, reduce violations by 2
            elif (student_id in self.DSBA_completed_modules and 
                'RMCE | RMCP' in self.DSBA_completed_modules[student_id]):
                violations = max(0, violations - 2)
            
            student_violations[student_id] = violations
            total_violations += violations

        return total_violations, student_suggestions, student_violations
    
    def getCost(self, schedule):
        if not self.isValidProgrammeRanges(schedule):
            return float('inf')
            
        module_dict = self.getIntakeSchedule(schedule)
        consecutivemoduleintake = self.countConsecutivemoduleintake(module_dict)
        rmce_violations = self.rmceintake(module_dict)
        concurrent_violations = self.concurrentModuleViolations(module_dict)
        se_student_violations, _, _ = self.calculate_SE_student_violations(module_dict)
        dsba_student_violations, _, _ = self.calculate_DSBA_student_violations(module_dict)
        
        hardContstraintViolations = (
            consecutivemoduleintake*1000 +
            rmce_violations*10000 +
            concurrent_violations*1000 +
            se_student_violations +
            dsba_student_violations)
        
        return self.hardConstraintPenalty * hardContstraintViolations

    def isValidProgrammeRanges(self, schedule):
        slots_per_programme = len(self.intakes) * self.slot_intake
        
        se_modules = schedule[:slots_per_programme]
        if not all(0 <= module <= 11 for module in se_modules):
            return False
            
        dsba_modules = schedule[slots_per_programme:]
        if not all(8 <= module <= 20 for module in dsba_modules):
            return False
            
        return True  
    
    def countConsecutivemoduleintake(self, programme_schedule):
        violations = 0
        for programme, intakes in programme_schedule.items():
            intakes_list = list(intakes.values())
            for i in range(len(intakes_list) - 1):
                intake_1 = intakes_list[i]
                intake_2 = intakes_list[i + 1]

                for module in intake_1:
                    if module in intake_2:
                        violations += 1
        return violations

    def rmceintake(self, programme_schedule):
        violations = 0
        required_intakes = ['Jan', 'Jun', 'Oct']

        for programme, intakes in programme_schedule.items():
            for intake in required_intakes:
                if intake in intakes:
                    if 'RMCE | RMCP' not in intakes[intake]:
                        violations += 1
        return violations
    
    def concurrentModuleViolations(self, programme_schedule):
        violations = 0
        matching_dict_SE = {}
        matching_dict_DSBA = {}
        concurrent_modules = ['BDAT', 'DM', 'MDA | NLP']
        
        # Check SE programme
        for intake, se_modules in programme_schedule['SE'].items():
            matching_modules = [module for module in concurrent_modules if module in se_modules]
            if matching_modules:
                matching_dict_SE[intake] = matching_modules
                  
        # Check DSBA programme
        for intake, dsba_modules in programme_schedule['DSBA'].items():
            matching_modules = [module for module in concurrent_modules if module in dsba_modules]
            if matching_modules:
                matching_dict_DSBA[intake] = matching_modules
            
        intakes = set(matching_dict_SE.keys()).union(matching_dict_DSBA.keys())
        
        # Compare for each intake
        for intake in intakes:
            if intake in matching_dict_SE and intake in matching_dict_DSBA:
                if matching_dict_DSBA[intake] != matching_dict_SE[intake]:
                    violations += 1
                elif matching_dict_SE[intake] != matching_dict_DSBA[intake]:
                    violations +=1
            else:
                violations +=1
                        
        return violations

    def removeDuplicatedModules(self, programme_schedule):
        for programme, intakes in programme_schedule.items():
            for intake, modules in intakes.items():
                seen_modules = set()
                unique_modules = []
                for module in modules:
                    if module not in seen_modules:
                        unique_modules.append(module)
                        seen_modules.add(module)
                intakes[intake] = unique_modules
        return programme_schedule
    
    def print_schedule(self, schedule):
        programme_schedule = self.getIntakeSchedule(schedule)
        
        # Remove duplicates before printing
        programme_schedule = self.removeDuplicatedModules(programme_schedule)

        print("Schedule for each intake and programme:")
        for programme, intakes in programme_schedule.items():
            print(f"\nProgramme: {programme}")
            for intake, modules in intakes.items():
                print(f"  Intake {intake}: {', '.join(modules) if modules else 'No modules assigned'}")

        se_violations, se_suggestions, se_student_violations = self.calculate_SE_student_violations(programme_schedule)
        dsba_violations, dsba_suggestions, dsba_student_violations = self.calculate_DSBA_student_violations(programme_schedule)
        
        print("\nViolations Summary:")
        print(f"Consecutive module intake violations: {self.countConsecutivemoduleintake(programme_schedule)}")
        print(f"RMCE module intake violations: {self.rmceintake(programme_schedule)}")
        print(f"Concurrent module violations: {self.concurrentModuleViolations(programme_schedule)}")
        print(f"SE student constraint violations: {se_violations}")
        print("\nViolations by Student:")
        for student_id, violations in se_student_violations.items():
            if violations > 0:  # Only print students with violations
                print(f"Student {student_id}: {violations} violations")
        print("\nSE Student Suggestions:")
        for student_id, modules in se_suggestions.items():
            print(f"{student_id}: {modules}") 
        
        print(f"DSBA student constraint violations: {dsba_violations}")
        print("\nViolations by Student:")
        for student_id, violations in dsba_student_violations.items():
            if violations > 0:  # Only print students with violations
                print(f"Student {student_id}: {violations} violations")
        print("\nDSBA Student Suggestions:")
        for student_id, modules in dsba_suggestions.items():
            print(f"{student_id}: {modules}")

def init_individual():
    slots_per_programme = len(schedule.intakes) * schedule.slot_intake
    se_modules = [random.randint(0, 11) for _ in range(slots_per_programme)]
    dsba_modules = [random.randint(8, 20) for _ in range(slots_per_programme)]
    return creator.individual(se_modules + dsba_modules)

def constrained_mutate(individual, indpb):
    slots_per_programme = len(schedule.intakes) * schedule.slot_intake
    for i in range(len(individual)):
        if random.random() < indpb:
            if i < slots_per_programme:
                individual[i] = random.randint(0, 11)
            else:
                individual[i] = random.randint(8, 20)
    return individual,
            
class ScheduleApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Schedule Generator")
        self.root.geometry("1200x800")

        # Upload Excel File
        self.upload_label = tk.Label(root, text="Upload Excel File:")
        self.upload_label.pack(pady=10)
        self.upload_button = tk.Button(root, text="Browse", command=self.upload_file)
        self.upload_button.pack(pady=5)

        # Label to Display File Name
        self.file_label = tk.Label(root, text="No file selected")
        self.file_label.pack(pady=5)
        
        # Generate Schedule Button
        self.generate_button = tk.Button(root, text="Generate Schedule", command=self.generate_schedule, state=tk.DISABLED)
        self.generate_button.pack(pady=10)

        # Create a Notebook (Tabbed Interface)
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Tab for SE Programme
        self.se_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.se_tab, text="SE Programme")

        # Tab for DSBA Programme
        self.dsba_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.dsba_tab, text="DSBA Programme")

        # Initialize Text Boxes for SE Programme
        self.se_schedule_label = tk.Label(self.se_tab, text="SE Programme Schedule:")
        self.se_schedule_label.pack(pady=5)
        self.se_schedule_text = scrolledtext.ScrolledText(self.se_tab, width=100, height=6)
        self.se_schedule_text.pack(pady=5, fill=tk.BOTH, expand=True)

        self.se_suggestions_label = tk.Label(self.se_tab, text="SE Student Suggestions:")
        self.se_suggestions_label.pack(pady=5)
        self.se_suggestions_text = scrolledtext.ScrolledText(self.se_tab, width=100, height=10)
        self.se_suggestions_text.pack(pady=5, fill=tk.BOTH, expand=True)

        self.se_violations_label = tk.Label(self.se_tab, text="SE Violations Details:")
        self.se_violations_label.pack(pady=5)
        self.se_violations_text = scrolledtext.ScrolledText(self.se_tab, width=100, height=6)
        self.se_violations_text.pack(pady=5, fill=tk.BOTH, expand=True)

        # Initialize Text Boxes for DSBA Programme
        self.dsba_schedule_label = tk.Label(self.dsba_tab, text="DSBA Programme Schedule:")
        self.dsba_schedule_label.pack(pady=5)
        self.dsba_schedule_text = scrolledtext.ScrolledText(self.dsba_tab, width=100, height=6)
        self.dsba_schedule_text.pack(pady=5, fill=tk.BOTH, expand=True)

        self.dsba_suggestions_label = tk.Label(self.dsba_tab, text="DSBA Student Suggestions:")
        self.dsba_suggestions_label.pack(pady=5)
        self.dsba_suggestions_text = scrolledtext.ScrolledText(self.dsba_tab, width=100, height=10)
        self.dsba_suggestions_text.pack(pady=5, fill=tk.BOTH, expand=True)

        self.dsba_violations_label = tk.Label(self.dsba_tab, text="DSBA Violations Details:")
        self.dsba_violations_label.pack(pady=5)
        self.dsba_violations_text = scrolledtext.ScrolledText(self.dsba_tab, width=100, height=6)
        self.dsba_violations_text.pack(pady=5, fill=tk.BOTH, expand=True)

    def upload_file(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")]
        )
        if file_path:
            try:
                self.file_path = file_path  
                self.data = pd.read_excel(self.file_path) 
                self.file_label.config(text=self.file_path.split('/')[-1])
                self.schedule = Schedule(hardConstraintPenalty=10, data=self.data)
                self.generate_button.config(state=tk.NORMAL)
                
            except Exception as e:
                messagebox.showerror("Error", f"Error loading file: {str(e)}")
                

    def generate_schedule(self):
        if not hasattr(self, 'file_path'):  
            messagebox.showerror("Error", "No file uploaded! Please upload an Excel file first.")
            return
        
        global schedule
        self.data = pd.read_excel(self.file_path)
        schedule = Schedule(hardConstraintPenalty=10, data=self.data)
        

        # GA
        pop_size = 200
        generations = 200
        prob_cx = 0.7
        prob_mut = 0.2
        random.seed(42)

        toolbox = base.Toolbox()
        creator.create('fitnessMin', base.Fitness, weights=(-1.0,))
        creator.create('individual', list, fitness=creator.fitnessMin)
        toolbox.register('individual', init_individual)
        toolbox.register('population', tools.initRepeat, list, toolbox.individual)
        toolbox.register('evaluate', lambda x: (schedule.getCost(x),))
        toolbox.register('select', tools.selTournament, tournsize=20)
        toolbox.register('mate', tools.cxUniform, indpb=0.15)
        toolbox.register('mutate', constrained_mutate, indpb=0.1)

        pop = toolbox.population(n=pop_size)
        stats = tools.Statistics(lambda x: x.fitness.values)
        stats.register('min', np.min)
        stats.register('avg', np.mean)

        hof = tools.HallOfFame(10)

        final_pop, logbook = algorithms.eaSimple(
            pop,
            toolbox,
            prob_cx,
            prob_mut,
            generations,
            stats,
            hof,
            True
        )

        # Get the best schedule
        best_schedule = hof[0]
        programme_schedule = schedule.getIntakeSchedule(best_schedule)
        programme_schedule = schedule.removeDuplicatedModules(programme_schedule)

        # Clear all text boxes
        self.se_schedule_text.delete(1.0, tk.END)
        self.se_suggestions_text.delete(1.0, tk.END)
        self.se_violations_text.delete(1.0, tk.END)
        self.dsba_schedule_text.delete(1.0, tk.END)
        self.dsba_suggestions_text.delete(1.0, tk.END)
        self.dsba_violations_text.delete(1.0, tk.END)

        # Display SE Programme Schedule
        self.se_schedule_text.insert(tk.END, "SE Programme Schedule:\n")
        for intake, modules in programme_schedule['SE'].items():
            self.se_schedule_text.insert(tk.END, f"  Intake {intake}: {', '.join(modules) if modules else 'No modules assigned'}\n")

        # Display DSBA Programme Schedule
        self.dsba_schedule_text.insert(tk.END, "DSBA Programme Schedule:\n")
        for intake, modules in programme_schedule['DSBA'].items():
            self.dsba_schedule_text.insert(tk.END, f"  Intake {intake}: {', '.join(modules) if modules else 'No modules assigned'}\n")

        # Display SE Student Suggestions
        se_violations, se_suggestions, se_student_violations = schedule.calculate_SE_student_violations(programme_schedule)
        self.se_suggestions_text.insert(tk.END, "SE Student Suggestions:\n")
        for student_id, modules in se_suggestions.items():
            self.se_suggestions_text.insert(tk.END, f"Student {student_id}: {modules}\n")

        # Display DSBA Student Suggestions
        dsba_violations, dsba_suggestions, dsba_student_violations = schedule.calculate_DSBA_student_violations(programme_schedule)
        self.dsba_suggestions_text.insert(tk.END, "DSBA Student Suggestions:\n")
        for student_id, modules in dsba_suggestions.items():
            self.dsba_suggestions_text.insert(tk.END, f"Student {student_id}: {modules}\n")

        # Display SE Violations Details
        self.se_violations_text.insert(tk.END, "SE Violations Summary:\n")
        self.se_violations_text.insert(tk.END, f"SE student constraint violations: {se_violations}\n")
        self.se_violations_text.insert(tk.END, "\nViolations by Student:\n")
        for student_id, violations in se_student_violations.items():
            if violations > 0:
                self.se_violations_text.insert(tk.END, f"Student {student_id}: {violations} violations\n")
        self.se_violations_text.insert(tk.END, "\n")        
        self.se_violations_text.insert(tk.END, "Common Violations Summary:\n")         
        self.se_violations_text.insert(tk.END, f"Consecutive module intake violations: {schedule.countConsecutivemoduleintake(programme_schedule)}\n")
        self.se_violations_text.insert(tk.END, f"RMCE module intake violations: {schedule.rmceintake(programme_schedule)}\n")
        self.se_violations_text.insert(tk.END, f"Concurrent module violations: {schedule.concurrentModuleViolations(programme_schedule)}\n")
        
        # Display DSBA Violations Details
        self.dsba_violations_text.insert(tk.END, "DSBA Violations Summary:\n")
        self.dsba_violations_text.insert(tk.END, f"DSBA student constraint violations: {dsba_violations}\n")
        self.dsba_violations_text.insert(tk.END, "\nViolations by Student:\n")
        for student_id, violations in dsba_student_violations.items():
            if violations > 0:
                self.dsba_violations_text.insert(tk.END, f"Student {student_id}: {violations} violations\n")
        self.dsba_violations_text.insert(tk.END, "\n")  
        self.dsba_violations_text.insert(tk.END, "Common Violations Summary:\n")        
        self.dsba_violations_text.insert(tk.END, f"Consecutive module intake violations: {schedule.countConsecutivemoduleintake(programme_schedule)}\n")
        self.dsba_violations_text.insert(tk.END, f"RMCE module intake violations: {schedule.rmceintake(programme_schedule)}\n")
        self.dsba_violations_text.insert(tk.END, f"Concurrent module violations: {schedule.concurrentModuleViolations(programme_schedule)}\n")
        
if __name__ == "__main__":
    root = tk.Tk()
    app = ScheduleApp(root)
    root.mainloop()
