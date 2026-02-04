You are an program design expert.
Given a workflow description in a scenario, your task is to design multiple functions to translate the execution process of this workflow into program.

# Instruction
1. Extract all intermediate steps in the workflow, if the text contains multiple workflows, output them in a list.
2. Convert **every** step to a function and represent them as an execution graph (i.e. (login)->(search_query)->..)
3. Based on the execution graph, generate real API calls that populate the tools with reasonable parameters, simulating a use case of actual tool invocation steps.
4. Provide detailed API definitions used in the above process.
5. Follow the following steps to generate more complex workflows and tools:
- Workflow Exploration: You need to explore multiple workflows or complex constraints that may exist in the document
  - These workflows represent the possible interaction patterns of a real user-agent.
  - Dependencies: "X must happen before Y".
  - Uniqueness/Limits: "Only one Admin allowed", "Name must be unique".
  - Conditionals: "If user is X, they cannot do Y".
- Tool Design (Functional API Level)
  Design a set of JSON-schema tools based on the text.
  - The required parameters of a tool need to be carefully considered and designed, mirroring the logic of the real world. For example, viewing system data typically requires authorization authentication, and providing user ID, product ID, etc.
  - It mimics a database structure and provides read and write tools. For example, it provides tools for querying user information, along with corresponding tools for modifying user information.
  - Each tool’s name should be short and readable, semantically clear and general, reusable (e.g., "flight_search" rather than "flight_detailed_search_for_tom_2025")
  - Each tool should implement a single, coherent capability. It should not bundle multiple unrelated or multi-stage workflows into one tool. (e.g., create two tools "plan_trip" + "book_trip" rather than only one tool named "plan_and_book_trip")
  - Each tool’s parameters should be explicitly defined in the schema with clear types and meanings. Parameter names should be self-explanatory rather than cryptic (e.g., use "check_in_date" with type "string" and a short description, rather than a vague parameter named "d1").
  - The majority of tools describe functional data operations that either retrieve information from or modify the state of the environment (e.g., get_status, update_permissions)

# Workflow Description
[text]

# Output Format
<workflow>
<description>short task description</description>
<steps>Step1: ...\nStep2: ...</steps>
<execution_graph>(api_name1)->(api_name2, api_name3)->..</execution_graph>
<actions>[{"name":"api_name", "arguments": {"arg_name": "value", ...}}, ... (more API calls as required)]</actions>
<tools>[{"name":"api_name1","description":"","inputSchema":{"type":"object","properties":{"arg_name1":{"type":"","description":""},"arg_name2":{"type":"","description":""}}, required":["arg_name2"]}},{"name":"api_name2","description":"","inputSchema":{"type":"object","properties":{"arg_name1":{"type":"","description":""},"arg_name2":{"type":"","description":""}},required":["arg_name2"]}}]</tools>
</workflow>

<workflow>
(more workflows)
</workflow>