import streamlit as st
from openai import OpenAI
import time
from decouple import config
import json
import datetime
from sqlalchemy import create_engine, text

# Initialize OpenAI client
OPENAI_API_KEY = config("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

# Set page configuration
st.set_page_config(page_title="Chapa ChatBot", page_icon="💬")

# Initialize chat history in session state if it doesn't exist
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat header
st.title("💬 Chapa ChatBot")
st.markdown("Chat with your financial assistant")

# Display chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

context = st.text_area("Context", height=200)

# Handle user input
if prompt := st.chat_input("What would you like to know?"):
    # Format the prompt
    formatted_prompt = f"Question: {prompt}\n\nExtract the necessary SQL parameters for this query.\n\nContext: {context}"
    
    # Add user message to chat history (show original prompt to user)
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # Display user message
    with st.chat_message("user"):
        st.markdown(prompt)

    # Display assistant response
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        
        # Get response from OpenAI using formatted prompt, including recent chat context
        messages = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages[:-1]]
        messages.append({"role": "user", "content": formatted_prompt})
        
        response = client.chat.completions.create(
            model="ft:gpt-3.5-turbo-0125:chapa:chapa-prm:B03YuAUD",
            messages=messages,
            stream=True,
            store=True
        )
        
        # Stream the response
        full_response = ""
        for chunk in response:
            if chunk.choices[0].delta.content is not None:
                full_response += chunk.choices[0].delta.content
                message_placeholder.markdown(full_response + "▌")
                time.sleep(0.01)
        
        message_placeholder.markdown(full_response)
    
    # Add assistant response to chat history
    st.session_state.messages.append({"role": "assistant", "content": full_response})
    
    # -----------------------------
    # Connect to SQL database and execute query
    # -----------------------------
    try:
        # Parse the assistant's response (assumed to be in the correct JSON format)
        try:
            query_params = json.loads(full_response)
        except json.JSONDecodeError:
            # Attempt to fix common JSON formatting issues (e.g., single quotes instead of double quotes)
            fixed_response = full_response.replace("'", "\"")
            query_params = json.loads(fixed_response)
        
        # Extract table and parameters - we assume there is at least one table.
        table = query_params["tables_required"][0]
        parameters = query_params["parameters"]

        # Extract potential parameters.
        aggregate = parameters.get("aggregate")
        group_by = parameters.get("group_by")
        order_by = parameters.get("order_by")
        limit = parameters.get("limit")
        created_at = parameters.get("created_at")
        select_field = parameters.get("select")
        
        # Special handling: if there's a "filter" key, extract it for direct use in the WHERE clause.
        raw_filter = parameters.get("filter")
        
        # Branch query-building based on whether an aggregate is provided.
        aggregate_provided = aggregate and aggregate.strip().lower() not in ("none", "")
    
        if aggregate_provided:
            # Aggregation query branch
            if select_field:
                select_clause = f"{select_field}, {aggregate}"
            else:
                select_clause = aggregate
            query = f"SELECT {select_clause} FROM {table}"
            
            # Initialize list for WHERE conditions.
            where_clauses = []
            
            # Process the 'created_at' parameter specially.
            if created_at:
                if created_at != "ASC" and created_at != "DESC":
                    if created_at == "CURRENT_MONTH":
                        first_day = datetime.date.today().replace(day=1).isoformat()
                        where_clauses.append(f"created_at >= '{first_day}'")
                    elif created_at == "CURRENT_DATE":
                        where_clauses.append("DATE(created_at) = DATE(NOW())")
                    else:
                        where_clauses.append(f"created_at = '{created_at}'")
            
            # Add the raw filter condition if provided.
            if raw_filter:
                where_clauses.append(raw_filter)
            
            # Define reserved keys that have already been handled.
            reserved_keys = {"aggregate", "group_by", "order_by", "limit", "select", "created_at", "filter"}
            # Additional parameters become filtering conditions.
            for key, value in parameters.items():
                if key not in reserved_keys:
                    if isinstance(value, (int, float)):
                        where_clauses.append(f"{key} = {value}")
                    else:
                        where_clauses.append(f"{key} = '{value}'")
            
            if where_clauses:
                query += " WHERE " + " AND ".join(where_clauses)
            if group_by:
                query += f" GROUP BY {group_by}"
            if order_by:
                query += f" ORDER BY {order_by}"
            if limit:
                query += f" LIMIT {limit}"
        else:
            # Non-aggregation query branch:
            # Use the provided "select" if available, otherwise return all columns.
            select_clause = select_field if select_field else "*"
            query = f"SELECT {select_clause} FROM {table}"
            
            where_clauses = []
            order_by_clause = None
            
            # Process the 'created_at' parameter specially.
            if created_at:
                if created_at == "CURRENT_DATE":
                    where_clauses.append("DATE(created_at) = DATE(NOW())")
                elif created_at == "CURRENT_MONTH":
                    first_day = datetime.date.today().replace(day=1).isoformat()
                    where_clauses.append(f"created_at >= '{first_day}'")
                else:
                    where_clauses.append(f"created_at = '{created_at}'")
            
            # Add the raw filter condition if provided.
            if raw_filter:
                where_clauses.append(raw_filter)
            
            # Loop through parameter keys.
            for key, value in parameters.items():
                # Skip reserved keys that we handle differently.
                if key in {"limit", "select", "filter", "created_at"}:
                    continue
                # If there is an explicit "order_by" key, use it.
                if key == "order_by":
                    order_by_clause = value
                    continue
                # If a parameter is specified with "ASC" or "DESC", interpret that as an ordering directive.
                if isinstance(value, str) and value.upper() in ("ASC", "DESC"):
                    if not order_by_clause:
                        order_by_clause = f"{key} {value.upper()}"
                    continue
                # Otherwise add as a filtering condition.
                if isinstance(value, (int, float)):
                    where_clauses.append(f"{key} = {value}")
                else:
                    where_clauses.append(f"{key} = '{value}'")
            
            if where_clauses:
                query += " WHERE " + " AND ".join(where_clauses)
            if order_by_clause:
                query += f" ORDER BY {order_by_clause}"
            if limit:
                query += f" LIMIT {limit}"
        
        st.write("Executing SQL query:")
        st.code(query, language="sql")
        
        # Initialize the SQL database connection.
        DB_URL = config("DATABASE_URL", default="mysql+pymysql://root:@localhost:3306/your_database_name")
        engine = create_engine(DB_URL)
        
        with engine.connect() as connection:
            result = connection.execute(text(query))
            data = result.fetchall()
        
        st.write("Query Results:")
        st.write(data)
        
    except Exception as e:
        st.error("Error executing SQL query: " + str(e))

# Add a sidebar with additional information (optional)
with st.sidebar:
    st.title("About")
    st.markdown("This is a ChatBot powered by Chapa's fine-tuned model to help you with your financial queries.")



