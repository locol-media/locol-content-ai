from persist_data import retrieve_dropdown_values, replace_dropdown_values, retrieve_llm_dropdown_values

# function to present a project list

def persist_projects(projects):
    return replace_dropdown_values(
            'projects', 
            projects
    )

def get_projects():
    return retrieve_dropdown_values( 'projects')


def persist_items(parent,items):
    return replace_dropdown_values(
            'items', 
            items,
            parent
    )

def get_items(parent):
    return retrieve_dropdown_values( 'items',parent)


def persist_channels(channels):
    return replace_dropdown_values(
            'channels', 
            channels
    )

def get_channels():
    return retrieve_dropdown_values( 'channels')

def get_llms():
    return retrieve_llm_dropdown_values( 'llms')