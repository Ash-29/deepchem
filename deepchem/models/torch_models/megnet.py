"""
Implementation of MEGNet class
"""
import torch
import torch.nn as nn
import torch.nn.functional as F

from deepchem.models.losses import Loss, L2Loss, SparseSoftmaxCrossEntropy
from deepchem.models.torch_models.layers import GraphNetwork as GN
from deepchem.models.torch_models import TorchModel

try:
  from torch_geometric.data import Batch as PyGBatch
except ModuleNotFoundError:
  raise ImportError("This module requires pytorch geometric")


class MEGNet(nn.Module):
  """MatErials Graph Network

  A model for predicting crystal and molecular properties using GraphNetworks.

  Example
  -------
  >>> import torch
  >>> from torch_geometric.data import Data as GraphData, Batch
  >>> from deepchem.models.torch_models import MEGNet
  >>> num_nodes, num_node_features = 5, 10
  >>> num_edges, num_edge_attrs = 5, 2
  >>> num_global_features = 4
  >>> node_features = torch.randn(num_nodes, num_node_features)
  >>> edge_attrs = torch.randn(num_edges, num_edge_attrs)
  >>> edge_index = torch.tensor([[0, 1, 2, 3, 4], [1, 2, 3, 4, 0]]).long()
  >>> global_features = torch.randn(num_global_features)
  >>> graph = GraphData(node_features, edge_index, edge_attrs, global_features=global_features)
  >>> batch = Batch()
  >>> batch = batch.from_graph_list([graph.to_pyg_graph()])
  >>> model = MEGNet(n_node_features=num_node_features, n_edge_features=num_edge_attrs, n_global_features=num_global_features)
  >>> pred = model(batch)

  Note
  ----
  This class requires torch-geometric to be installed.
  """

  def __init__(self,
               n_node_features: int = 32,
               n_edge_features: int = 32,
               n_global_features: int = 32,
               n_blocks: int = 1,
               is_undirected: bool = True,
               residual_connection: bool = True,
               mode: str = 'regression',
               n_classes: int = 2,
               n_tasks: int = 1):
    """

    Parameters
    ----------
    n_node_features: int
      Number of features in a node
    n_edge_features: int
      Number of features in a edge
    n_global_features: int
      Number of global features
    n_blocks: int
      Number of GraphNetworks block to use in update
    is_undirected: bool, optional (default True)
      True when the graph is undirected graph , otherwise False
    residual_connection: bool, optional (default True)
      If True, the layer uses a residual connection during training
    n_tasks: int, default 1
      The number of tasks
    mode: str, default 'regression'
      The model type - classification or regression
    n_classes: int, default 2
      The number of classes to predict (used only in classification mode).
    """
    super(MEGNet, self).__init__()
    try:
      from torch_geometric.nn import Set2Set
    except ModuleNotFoundError:
      raise ImportError("MEGNet model requires torch_geometric to be installed")

    if mode not in ['classification', 'regression']:
      raise ValueError("mode must be either 'classification' or 'regression'")
    self.n_node_features = n_node_features
    self.n_edge_features = n_edge_features
    self.n_global_features = n_global_features
    self.megnet_blocks = nn.ModuleList()
    self.n_blocks = n_blocks
    for i in range(n_blocks):
      self.megnet_blocks.append(
          GN(n_node_features=n_node_features,
             n_edge_features=n_edge_features,
             n_global_features=n_global_features,
             is_undirected=is_undirected,
             residual_connection=residual_connection))
    self.n_tasks = n_tasks
    self.mode = mode
    self.n_classes = n_classes

    self.set2set_nodes = Set2Set(
        in_channels=n_node_features, processing_steps=3, num_layers=1)
    self.set2set_edges = Set2Set(
        in_channels=n_edge_features, processing_steps=3, num_layers=1)

    self.dense = nn.Sequential(
        nn.Linear(
            in_features=2 * n_node_features + 2 * n_edge_features +
            n_global_features,
            out_features=32), nn.Linear(in_features=32, out_features=16))

    if self.mode == 'regression':
      self.out = nn.Linear(in_features=16, out_features=n_tasks)
    elif self.mode == 'classification':
      self.out = nn.Linear(in_features=16, out_features=n_tasks * n_classes)

  def forward(self, pyg_batch: PyGBatch):
    """
    Parameters
    ----------
    pyg_batch: PyGBatch
      A pytorch-geometric batch of graphs where node attributes are stores
      as pyg_batch['x'], edge_index in pyg_batch['edge_index'], edge features
      in pyg_batch['edge_attr'], global features in pyg_batch['global_features']

    Returns
    -------
    torch.Tensor: Predictions for the graph
    """
    node_features = pyg_batch['x']
    edge_index, edge_features = pyg_batch['edge_index'], pyg_batch['edge_attr']
    global_features = pyg_batch['global_features']
    batch = pyg_batch['batch']

    for i in range(self.n_blocks):
      node_features, edge_features, global_features = self.megnet_blocks[i](
          node_features, edge_index, edge_features, global_features, batch)

    node_features = self.set2set_nodes(node_features, batch)
    edge_features = self.set2set_edges(edge_features, batch[edge_index[0]])
    out = torch.cat([node_features, edge_features, global_features], axis=1)
    out = self.out(self.dense(out))

    if self.mode == 'classification':
      if self.n_tasks == 1:
        logits = out.view(-1, self.n_classes)
        softmax_dim = 1
      else:
        logits = out.view(-1, self.n_tasks, self.n_classes)
        softmax_dim = 2
      proba = F.softmax(logits, dim=softmax_dim)
      return proba, logits
    elif self.mode == 'regression':
      return out


class MEGNetModel(TorchModel):
  """MEGNet Model

  """
  def __init__(self,
               n_node_features: int = 32,
               n_edge_features: int = 32,
               n_global_features: int = 32,
               n_blocks: int = 1,
               is_undirected: bool = True,
               residual_connection: bool = True,
               mode: str = 'regression',
               n_classes: int = 2,
               n_tasks: int = 1,
               **kwargs):
    """

    Parameters
    ----------
    n_node_features: int
      Number of features in a node
    n_edge_features: int
      Number of features in a edge
    n_global_features: int
      Number of global features
    n_blocks: int
      Number of GraphNetworks block to use in update
    is_undirected: bool, optional (default True)
      True when the model is used on undirected graphs otherwise false
    residual_connection: bool, optional (default True)
      If True, the layer uses a residual connection during training
    n_tasks: int, default 1
      The number of tasks
    mode: str, default 'regression'
      The model type - classification or regression
    n_classes: int, default 2
      The number of classes to predict (used only in classification mode).
    kwargs: Dict
      kwargs supported by TorchModel
    """
    model = MEGNet(
        n_node_features=n_node_features,
        n_edge_features=n_edge_features,
        n_global_features=n_global_features,
        n_blocks=n_blocks,
        is_undirected=is_undirected,
        residual_connection=residual_connection,
        mode=mode,
        n_classes=n_classes,
        n_tasks=n_tasks)
    if mode == 'regression':
      loss: Loss = L2Loss()
      output_types = ['prediction']
    elif mode == 'classification':
      loss = SparseSoftmaxCrossEntropy()
      output_types = ['prediction', 'loss']
    super(MEGNetModel, self).__init__(
        model, loss=loss, output_types=output_types, **kwargs)

  def _prepare_batch(self, batch):
    """Creates batch data for MEGNet model

    Note
    ----
    Ideally, we should only override default_generator method. But the problem
    here is that we _prepare_batch of TorchModel only supports non-graph
    data types. Hence, we are overriding it here. This should be fixed
    some time in the future.
    """
    try:
      from torch_geometric.data import Batch
    except ModuleNotFoundError:
      raise ImportError("This module requires PyTorch Geometric")

    # We convert deepchem.feat.GraphData to a PyG graph and then
    # batch it.
    graphs, labels, weights = batch
    # The default_generator method returns an array of dc.feat.GraphData objects
    # nested inside a list. To access the nested array of graphs, we are
    # indexing by 0 here.
    graph_list = [graph.to_pyg_graph() for graph in graphs[0]]
    pyg_batch = Batch()
    pyg_batch = pyg_batch.from_data_list(graph_list)

    _, labels, weights = super(MEGNetModel, self)._prepare_batch(([], labels,
                                                                  weights))

    return pyg_batch, labels, weights
