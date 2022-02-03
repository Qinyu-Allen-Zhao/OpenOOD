from __future__ import print_function

import numpy as np
import torch
from sklearn.mixture import GaussianMixture
from tqdm import tqdm

from .mds_tools import process_feature_type, reduce_feature_dim, tensor2list


@torch.no_grad()
def get_GMM_stat(model, train_loader, num_clusters_list, feature_type_list,
                 reduce_dim_list):
    """ Compute GMM.
    Args:
        model (nn.Module): pretrained model to extract features
        train_loader (DataLoader): use all training data to perform GMM
        num_clusters_list (list): number of clusters for each layer
        feature_type_list (list): feature type for each layer
        reduce_dim_list (list): dim-reduce method for each layer

    return: feature_mean: list of class mean
            feature_prec: list of precisions
            component_weight_list: list of component
            transform_matrix_list: list of transform_matrix
    """
    feature_mean_list, feature_prec_list = [], []
    component_weight_list, transform_matrix_list = [], []
    num_layer = len(num_clusters_list)
    feature_all = [None for x in range(num_layer)]
    label_list = []
    # collect features
    for batch in tqdm(train_loader, desc='Compute GMM Stats [Collecting]'):
        data = batch['data_aux'].cuda()
        label = batch['label']
        _, feature_list = model(data, return_feature_list=True)
        label_list.extend(tensor2list(label))
        for layer_idx in range(num_layer):
            feature_type = feature_type_list[layer_idx]
            feature_processed = process_feature_type(feature_list[layer_idx],
                                                     feature_type)
            if isinstance(feature_all[layer_idx], type(None)):
                feature_all[layer_idx] = tensor2list(feature_processed)
            else:
                feature_all[layer_idx].extend(tensor2list(feature_processed))
    label_list = np.array(label_list)
    # reduce feature dim and perform gmm estimation
    for layer_idx in tqdm(range(num_layer),
                          desc='Compute GMM Stats [Estimating]'):
        feature_sub = np.array(feature_all[layer_idx])
        transform_matrix = reduce_feature_dim(feature_sub, label_list,
                                              reduce_dim_list[layer_idx])
        feature_sub = np.dot(feature_sub, transform_matrix)
        # GMM estimation
        gm = GaussianMixture(
            n_components=num_clusters_list[layer_idx],
            random_state=0,
            covariance_type='tied',
        ).fit(feature_sub)
        feature_mean = gm.means_
        feature_prec = gm.precisions_
        component_weight = gm.weights_

        feature_mean_list.append(torch.Tensor(feature_mean).cuda())
        feature_prec_list.append(torch.Tensor(feature_prec).cuda())
        component_weight_list.append(torch.Tensor(component_weight).cuda())
        transform_matrix_list.append(torch.Tensor(transform_matrix).cuda())

    return feature_mean_list, feature_prec_list, \
        component_weight_list, transform_matrix_list


def compute_GMM_score(model,
                      data,
                      feature_mean,
                      feature_prec,
                      component_weight,
                      transform_matrix,
                      layer_idx,
                      feature_type_list,
                      return_pred=False):
    """ Compute GMM.
    Args:
        model (nn.Module): pretrained model to extract features
        data (DataLoader): input one training batch
        feature_mean (list): a list of torch.cuda.Tensor()
        feature_prec (list): a list of torch.cuda.Tensor()
        component_weight (list): a list of torch.cuda.Tensor()
        transform_matrix (list): a list of torch.cuda.Tensor()
        layer_idx (int): index of layer in interest
        feature_type_list (list): a list of strings to indicate feature type
        return_pred (bool): return prediction and confidence, or only conf.

    return:
        pred (torch.cuda.Tensor):
        prob (torch.cuda.Tensor):
    """
    # extract features
    pred_list, feature_list = model(data, return_feature_list=True)
    pred = torch.argmax(pred_list, dim=1)
    feature_list = process_feature_type(feature_list[layer_idx],
                                        feature_type_list[layer_idx])
    feature_list = torch.mm(feature_list, transform_matrix[layer_idx])
    # compute prob
    for cluster_idx in range(len(feature_mean[layer_idx])):
        zero_f = feature_list - feature_mean[layer_idx][cluster_idx]
        term_gau = -0.5 * torch.mm(torch.mm(zero_f, feature_prec[layer_idx]),
                                   zero_f.t()).diag()
        prob_gau = torch.exp(term_gau)
        if cluster_idx == 0:
            prob_matrix = prob_gau.view([-1, 1])
        else:
            prob_matrix = torch.cat((prob_matrix, prob_gau.view(-1, 1)), 1)
    prob = torch.mm(prob_matrix, component_weight[layer_idx].view(-1, 1))
    if return_pred:
        return pred, prob
    else:
        return prob
