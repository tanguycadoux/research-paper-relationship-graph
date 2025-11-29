import networkx as nx
import plotly.graph_objects as go
from datetime import datetime
from dateutil.relativedelta import relativedelta
import numpy as np


def build_user_refs_graph(user):
    G = nx.DiGraph()

    user_pubs = user.userpublication_set.select_related('publication')

    for upub in user_pubs:
        pub = upub.publication
        G.add_node(pub.pk, publication=pub)

        refs = pub.outgoing_references.all()
        for ref in refs:
            target = ref.target
            G.add_node(target.pk, publication=target)
            G.add_edge(pub.pk, target.pk)

    return G

def plotly_graph_from_nx(G, user_pub_ids):
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
    for node in G.nodes():
        if node in user_pub_ids:
            node_colors.append("lightgreen")
        else:
            node_colors.append("lightblue")
    
    edge_x, edge_y = [], []
    for edge in G.edges():
        x0 = G.nodes[edge[0]]['publication'].publication_date if G.nodes[edge[0]]['publication'].publication_date else null_year
        x1 = G.nodes[edge[1]]['publication'].publication_date if G.nodes[edge[1]]['publication'].publication_date else null_year
        y0 = node_y[list(G.nodes).index(edge[0])]
        y1 = node_y[list(G.nodes).index(edge[1])]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])

    edge_trace = go.Scatter(x=edge_x, y=edge_y,
                            line=dict(width=1, color='#888'),
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
            line_width=2
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
    interp_start_year = min_year - min_year%interp_step + interp_step
    interp_end_year   = max_year - max_year%interp_step

    x_ticks = [
        [null_year, min_year],
        ["Non défini", min_year]
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
            showgrid=False,
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
