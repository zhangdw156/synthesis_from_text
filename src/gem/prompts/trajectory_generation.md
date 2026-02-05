You are tasked with generating high-quality multi-turn dialogue trajectories based on a given text document. The trajectory should demonstrate an AI assistant helping users complete tasks while strictly following domain-specific rules and constraints.

You will be provided with:
- A list of Available Tool Candidates;
- A source text document that contains the description of the scenario and task steps;

## Completion Requirements
1. System Prompt: Extract and explicitly state ALL important domain-specific rules and constraints from the source text document.
Example:
<system>
You are a agent specialized in retail domain. Here are some basic rules to follow:
- An order can only be cancelled if its status is 'pending' ...
- Modify action can only be called once, and will change the order status to 'pending (items modified)' ...
- ...
</system>

2. User Task: Create natural, progressive user requests that test the system’s rule enforcement and constraint handling. Here are some features:
- Naturalness: Requests should reflect real-world use cases.
- Ambiguity: User requests are often incomplete, requiring the assistant to analyze or clarify them.
  Example: <user> I want to cancel order #W2575533. </user> (the user do not provide the specific reason, and the assistant should ask for clarification); <user> Recommend me a desktop. I often go out. </user> (the user do not explicitly state the attribute of the item, but the assistant should analyze and know it based on the stated preference)
- Consistent: User’s intention, persona, and their behavior should be consistent across the dialogue.
- Complex: The user’s request is challenging enough to test the assistant’s ability. Users can make requests that violate domain rules and are not allowed to alert the assistant (e.g., do not ask the model to verify the order status first).
  At least in one turn, the user’s request is very complex and require assistant to handle it carefully.
  Example 1:
  <user> I need to make several changes to my order #W2575533. Can I change the E-Reader to a different size, swap the Garden Hose color, and also update my shipping address </user>
  (Requires assistant to: check order status, verify each item can be modified, handle address change separately, remind about one-time modification limit)
  Example 2:
  <user> Check my tire pressures. If any of them are low, find me the nearest service station and also check if I have enough fuel to get there </user>
  (Requires: check tire pressure, evaluate condition, conditionally call find_nearest_shop, check fuel level, calculate if sufficient)
  Example 3:
  <user> I’m planning a three-day trip starting from Hangzhou, and I need help creating an itinerary. One more thing about the second day - I’m trying to be smart about my budget. If I end up booking a luxury hotel that costs 800 CNY or more per night, then I need to be more careful with other expenses: my total spending on both restaurants (lunch and dinner) should stay under 350 CNY, both restaurants should be rated at least 4.0 stars, and the afternoon attraction ticket needs to be less than 120 CNY. </user>
  (Requires: check multiple constraints)

3. Assistant: Generate Responses that Demonstrate Rule Enforcement, Clear Communication, and Intelligent Problem-Solving:
- Reasoning and Adaptive Planning: The Assistant should reason through problem contexts and plan appropriate steps. Sometimes users may not be able to directly provide the parameters for tool calls, and the assistant needs to accurately consider whether the parameter values can be obtained through other information and tools.
- Precondition Checks: Before executing tasks, the Assistant should validate any necessary preconditions (e.g., authenticating identity, verifying the status of an order).
- Domain Rules and Constraints: The Assistant must follow domain-specific rules at all times. Ensure the assistant’s tool call and response genuinely addresses those requirements.
- User-Centric Principle: The Assistant must accurately understand and satisfy all user needs and preferences without breaking domain rules. For example, if user states "prefers A, wants B, and tell me C", the assistant should satisfy all requirements.
- No Hallucination:
  - Context Faithfulness: Maintain absolute fidelity to tool outputs. If data contradicts user expectations, explicitly report the discrepancy instead of distorting facts to force a match.
  - Tool call arguments: The Assistant must only use argument values that are explicitly provided or implied by the user. It must not fabricate IDs, names, or other parameters; if any required value is missing or unclear, the Assistant should ask the user to supply it before calling the tool.
- Consequence-aware: Before executing any write operation that modifies the environment, the Assistant must actively think and assess its impact. For changes that are irreversible, the assistant should obtain explicit user confirmation before proceeding.
- Limitations: If the current request is beyond the assistant’s ability, the Assistant must communicate this limitation clearly. For example: If the user’s needs are beyond domain rules, the Assistant must explain the limitation but should still respect the user’s needs. (e.g., "I cannot do A, but I can do B. Should I proceed with B?" -> Wait for confirmation).
- Correct Tool Calls:
  - Tool call format: `<func>{"name":"exact_tool_name", "arguments": {"arg": "value"}}</func>`.
  - Exact Matching: The Assistant must ensure that tool calls exactly match the available candidate tools. Calling tools that do not exist is prohibited.
  - Parameter Validation: The arguments passed to the tools must exactly match the tool definitions, including the required parameters. The Assistant should avoid any missing parameters and validate that the values are accurate.

4. Tool Responses: Structured and Complete
- Correctness of Tool Call: A success response should only be returned if the tool call is correct (including both the correct function name and parameters). If any part of the tool call is incorrect or incomplete, the tool should return a failure response, indicating what went wrong.
- Success Response: The tool’s success response must return all relevant information in a well-structured format (e.g., JSON). This includes not just the requested data, but also any other relevant details, such as order ID, status, product ID, item ID, etc., in case the user requires further context.
- Error Response: When there is an error, the tool should return only the error message. No additional information should be provided that directly aids the Assistant in recovering from the error.
- Consistent Response Structure: The format and content of the tool’s responses should remain consistent throughout the conversation. This ensures clarity and reliability in the tool’s output, helping to maintain a smooth user experience.
- Don’t confuse the order between turns:
  - a user message or tool result should be followed by an assistant message. (<user>...</user> / <tool>...</tool> -> <assistant>...</assistant>)
  - If the assistant message includes a tool call, it can be followed by a tool message; (<assistant>...<func>...</func></assistant> -> <tool>...</tool>)
  - otherwise, it should be followed by a user message. (<assistant> ... </assistant> -> <user> ... </user>)
  - Tool result cannot followed by user message. (MUST NOT OUTPUT: <tool>...</tool> -> <user>...</user> (incorrect example))

## Other Requirements
- Always use English.
- The whole trajectory should be reasonable, realistic (conform to real-world dialogue scenarios and interactions), and fit the context of multi-turn tool usage.
- Don’t confuse the order between rounds: a user message or tool result should be followed by an assistant message. If the assistant message includes a tool call, it can be followed by a tool message; otherwise, it should be followed by a user message. Tool result cannot followed by user message.
- Tool call format:
<func>
{"name": "exact_tool_name_in_toolsets", "arguments": {"arg": "value"}}
</func>

## Given Inputs
### Available Tool Candidates
{candidate_tools}

### A source text document consisting of Task Steps Description
{current_task}

## Output Format

You must STRICTLY follow the following output format.
Ensure ALL tags are properly opened and closed. Conversations like "<tool> ... </assistant>", "<assistant>..</user>" are wrong!!!

<system>
...
</system>
<user>
...
</user>
<assistant>
...
<func>
{"name": "...", "arguments": {...}}
</func>
</assistant>
<tool>
...
</tool>