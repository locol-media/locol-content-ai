import sqlite3
from sqlite3 import Error
import json
from db_manager import get_db_connection

def prompt_rag(question,context):
    template = f"""

        You are an assistant for generating content. 
        Use the following pieces of retrieved context to answer the question.
        If you don't know the answer, say that you don't know.

        Generate output in HTML format using only p, b,i,em,u,a,ul,ol,br,h1,h2 elements.
        Return only the content itself: no introduction or commentary about what you
        wrote, and no markdown code fences.

        Question: {question}
        Context: {context}
        """
    
    return template

def prompt(question):
    template =  f"""
        You are an assistant for generating content. 
        If you don't know the answer, use your general knowledge or search the web.

        Generate output in HTML format using only p, b,i,em,u,a,ul,ol,br,h1,h2 elements.
        Return only the content itself: no introduction or commentary about what you
        wrote, and no markdown code fences.

        Question: {question}
        """
    return template


def get_prompt_templates(selected):
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    sql = f'''
	 SELECT DISTINCT p.id,p.name,p.template,
	  JSON_GROUP_ARRAY(t.tag) AS tag_array
	    FROM prompts p 
        JOIN prompt_tags t on t.prompt_id = p.id
       WHERE p.id IN (
	   SELECT DISTINCT p.id
    	FROM prompts p 
        JOIN prompt_tags t on t.prompt_id = p.id
        WHERE t.tag IN (
            SELECT tag FROM channel_tags ct
            WHERE channel_id = ?))
       GROUP BY p.id,p.name,p.template;
    '''
    cur = conn.cursor()
    cur.execute(sql,[selected])
    rows = cur.fetchall()
    conn.close()
    return json.dumps([dict(row) for row in rows])

def get_prompt_template_by_platform(platform_name):
    """
    Get prompt template by platform name from prompt table with tag platform:platform_name
    
    Parameters:
        platform_name (str): The platform name to search for
        
    Returns:
        dict: Prompt template data or None if not found
    """
    conn = get_db_connection()
    if conn is None:
        return None
        
    conn.row_factory = sqlite3.Row
    
    # Look for prompt with tag "platform:platform_name"
    platform_tag = f"platform:{platform_name}"
    
    sql = '''
        SELECT DISTINCT p.id, p.name, p.template,
               JSON_GROUP_ARRAY(t.tag) AS tag_array
        FROM prompts p
        JOIN prompt_tags t ON t.prompt_id = p.id
        WHERE p.id IN (
            SELECT DISTINCT p.id
            FROM prompts p
            JOIN prompt_tags t ON t.prompt_id = p.id
            WHERE t.tag = ?
        )
        GROUP BY p.id, p.name, p.template
        LIMIT 1;
    '''
    
    try:
        cur = conn.cursor()
        cur.execute(sql, [platform_tag])
        row = cur.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        else:
            return None
            
    except Error as e:
        print(f"Error retrieving prompt template for platform {platform_name}: {e}")
        if conn:
            conn.close()
        return None