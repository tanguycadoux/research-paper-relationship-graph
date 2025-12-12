import networkx as nx
import plotly.graph_objects as go
from datetime import datetime
from dateutil.relativedelta import relativedelta
import numpy as np


def map_value(value, from_min, from_max, to_min, to_max):
    return (value - from_min) * (to_max - to_min) / (from_max - from_min) + to_min

def build_user_refs_graph(user):
    G = nx.DiGraph()

    user_pubs = user.userpublication_set.select_related('publication')

    for upub in user_pubs:
        pub = upub.publication
        G.add_node(pub.pk, publication=pub)

        refs = pub.outgoing_references.all()
        for ref in refs:
            target = ref.target
            incoming_refs = len(target.incoming_references.all())
            G.add_node(target.pk, publication=target, cited_by_nb=incoming_refs)
            G.add_edge(pub.pk, target.pk)       
    return G

def build_pub_graph(pub):
    G = nx.DiGraph()

    G.add_node(pub.pk, publication=pub)

    refs = pub.outgoing_references.all()
    for ref in refs:
        target = ref.target
        incoming_refs = len(target.incoming_references.all())
        G.add_node(target.pk, publication=target, cited_by_nb=incoming_refs)
        G.add_edge(pub.pk, target.pk)       
    return G

def plotly_graph_from_nx(G, source_pubs_ids):
    y_counter = 0
    node_x, node_y, node_text = [], [], []

    min_date = datetime.now().date()
    max_date = datetime.strptime('1900', "%Y").date()
    for node in G.nodes():
        pub = G.nodes[node]['publication']
        if pub.publication_date:
            min_date = min(min_date, pub.publication_date)
            max_date = max(max_date, pub.publication_date)
    
    null_year = min_date.year-5
        
    for node in G.nodes():
        pub = G.nodes[node]['publication']

        if pub.publication_date:
            x = pub.publication_date
        else:
            x = null_year
        
        node_x.append(x)
        node_y.append(y_counter)
        node_text.append(pub.title or pub.doi)

        y_counter += 1

    node_colors = []
    cited_by_data = {
        'min': len(G.nodes()),
        'max': 0,
    }
    for node in G.nodes():
        if node not in source_pubs_ids:
            cited_by_data['min'] = min(G.nodes[node]['cited_by_nb'], cited_by_data['min'])
            cited_by_data['max'] = max(G.nodes[node]['cited_by_nb'], cited_by_data['max'])
            
    for node in G.nodes():
        if node in source_pubs_ids:
            node_colors.append("lightgreen")
        else:
            l = map_value(G.nodes[node]['cited_by_nb'],
                          cited_by_data['min'], cited_by_data['max'],
                          25, 75)
            
            node_colors.append(f"hsl(240, 80%, {l}%)")
    
    edge_x, edge_y = [], []
    for edge in G.edges():
        x0 = G.nodes[edge[0]]['publication'].publication_date if G.nodes[edge[0]]['publication'].publication_date else null_year
        x1 = G.nodes[edge[1]]['publication'].publication_date if G.nodes[edge[1]]['publication'].publication_date else null_year
        y0 = node_y[list(G.nodes).index(edge[0])]
        y1 = node_y[list(G.nodes).index(edge[1])]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])

    edge_trace = go.Scatter(x=edge_x, y=edge_y,
                            line=dict(width=1.5, color='black'),
                            hoverinfo='none', mode='lines')
    node_trace = go.Scatter(
        x=node_x, y=node_y,
        text=node_text,
        mode='markers',
        hovertext=node_text,
        hoverinfo='text',
        marker=dict(
            size=20,
            color=node_colors,
                line=dict(
                color='black',
                width=1.5,
            ),
        ),
        textposition='top center'
    )

    fig = go.Figure(data=[edge_trace, node_trace],
                    layout=go.Layout(
                        showlegend=False,
                        hovermode='closest',
                        margin=dict(b=5,l=5,r=5,t=5),
                        autosize=True,
                        width=None,
                        height=600,
                    ))
    
    min_year = min_date.year
    max_year = max_date.year+1

    interp_step = 5
    interp_start_year = min_year - min_year%interp_step
    interp_end_year   = max_year - max_year%interp_step

    x_ticks = [
        [null_year],
        ["Non défini"]
    ]
    for year in range(interp_start_year, interp_end_year+interp_step, interp_step):
        x_ticks[0].append(year)
        x_ticks[1].append(year)

    x_ticks[0].append(max_year)
    x_ticks[1].append(max_year)

    fig.update_xaxes(
        tickvals=x_ticks[0],
        ticktext=x_ticks[1]
    )
    fig.update_layout(
        plot_bgcolor='white',
        xaxis=dict(
            showgrid=True,
            gridcolor='#CCC',
            showline=True,
            linecolor='black',
            type='date'
        ),
        yaxis=dict(
            showgrid=False,
            zeroline=False,
            showline=False,
            showticklabels=False
        )
    )
    return fig
