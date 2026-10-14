"""Code Explainer: turns the source code of one module into a business logic document.

Python does what fixed logic can do; AI agents do what needs understanding. The modules, in the order
the work passes through them:

  store          paths, config.json, JSON files, file fingerprints
  notes          the module notes: business domain, what the business team says
  java_index     reads Java, SQL and configuration files; lists what must be explained
  run_check      the execution check: runs code that can be run on its own
  inventory      cuts the module into work items, each with its checklist
  rules_check    checks what the extract agent wrote
  flow_check     checks the flow diagram and the scenarios in it
  verify_check   checks what the second reviewer wrote, and the module overview
  state          the state of each work item, from the files that exist
  tasks          the task line each agent is given
  pipeline       prepare and step: the run driven from Copilot Chat
  runner         run: the same work, with Python calling the model itself
  coverage       the coverage report
  markdown       helpers that write Markdown
  document       the final document
  calibrate      measures the document against the rules an SME listed
  cli            the command line
"""
