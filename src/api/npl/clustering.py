

"""
Clustering utilities for content items using embeddings.

This module provides functions to perform clustering on text embeddings
and extract top keywords per cluster for interpretability.
"""

from typing import List, Dict, Tuple
import numpy as np
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer


def perform_kmeans(embeddings: np.ndarray, k: int) -> List[int]:
    """
    Perform KMeans clustering on embeddings.

    Args:
        embeddings (np.ndarray): Matrix of shape (n_samples, embedding_dim).
        k (int): Number of clusters.

    Returns:
        List[int]: Cluster assignments for each sample.
    """
    kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = kmeans.fit_predict(embeddings)
    return labels


def extract_top_terms_per_cluster(
    texts: List[str], labels: List[int], top_n: int = 5
) -> Dict[int, List[Tuple[str, float]]]:
    """
    Extract top terms per cluster using TF-IDF.

    Args:
        texts (List[str]): Original documents/texts.
        labels (List[int]): Cluster assignments for each text.
        top_n (int): Number of top terms per cluster.

    Returns:
        Dict[int, List[Tuple[str, float]]]: Mapping from cluster -> list of (term, score).
    """
    vectorizer = TfidfVectorizer(stop_words="english", max_features=5000)
    tfidf_matrix = vectorizer.fit_transform(texts)
    terms = vectorizer.get_feature_names_out()

    cluster_terms: Dict[int, List[Tuple[str, float]]] = {}
    for cluster_id in np.unique(labels):
        cluster_indices = [i for i, lbl in enumerate(labels) if lbl == cluster_id]
        cluster_tfidf = tfidf_matrix[cluster_indices].mean(axis=0).A1
        top_indices = cluster_tfidf.argsort()[-top_n:][::-1]
        cluster_terms[cluster_id] = [(terms[idx], cluster_tfidf[idx]) for idx in top_indices]

    return cluster_terms