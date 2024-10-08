import matplotlib.pyplot as plt
import os
import numpy as np
import pandas as pd
import slideflow as sf
import torch
from PIL import Image, ImageDraw, ImageFont
from sklearn.metrics import auc
from lifelines.utils import concordance_index
from sklearn.calibration import calibration_curve
from sksurv.metrics import cumulative_dynamic_auc
import scipy.stats as stats
from sklearn.metrics import precision_recall_curve, average_precision_score, roc_curve, auc
import seaborn as sns
import logging
import sys

def visualize_activations(config : dict, dataset : str,
                          tfrecord_dir : str, bag_dir : str, target : str, save_string : str):
    """
    Visualize the activations based on the configuration

    Args:
        config: The configuration dictionary
        dataset: The dataset string
        tfrecord_dir: Directory with tfrecords
        bag_dir: Directory with bags
        target: The target variable
        save_string: The save string
    
    Returns:
        None

    """
    #Retrieve features from bags
    dts_ftrs = sf.DatasetFeatures.from_bags(bag_dir)

    #Get slide-level embeddings

    #Create slidemap using these features
    slide_map = sf.SlideMap.from_features(dts_ftrs)
    if 'umap' in config['experiment']['visualization'] or 'mosaic' in config['experiment']['visualization']:
        logging.info("Visualizing activations...")
        labels, unique_labels = dataset.labels(target, format='name')
            
        slide_map.label_by_slide(labels)
        #Make a new directory inside visualizations
        if not os.path.exists(f"experiments/{config['experiment']['project_name']}/visualizations/patch_level_umap_label_{save_string}_{dataset}"):
            os.makedirs(f"experiments/{config['experiment']['project_name']}/visualizations/patch_level_umap_label_{save_string}_{dataset}")
        slide_map.save_plot(
            filename=f"experiments/{config['experiment']['project_name']}/visualizations/patch_level_umap_label_{save_string}_{dataset}",
            title="Patch UMAP, by slide label",
            subsample=2000
        )

        plt.close()
    
        print(dts_ftrs)
        #Take mean of features, to get slide-level features
        slide_ftrs = dts_ftrs.mean(axis=1)
        print(slide_ftrs)
        #Create a new slide map
        slide_map = sf.SlideMap.from_features(slide_ftrs)
        slide_map.label_by_slide(labels)
        slide_map.save_plot(
            filename=f"experiments/{config['experiment']['project_name']}/visualizations/slide_level_umap_label_{save_string}_{dataset}",
            title="Slide-level UMAP, by label",
            subsample=2000
        )
        plt.close()
    if 'mosaic' in config['experiment']['visualization']:

        #TOFIX: DOES NOT WORK NOW!
        logging.info("Building mosaic...")
        # Get list of all directories in the tfrecords dir with full path
        try:
            mosaic =  slide_map.build_mosaic()
            mosaic.save(
                filename=f"experiments/{config['experiment']['project_name']}/visualizations/slide_level_mosaic_{save_string}.png"
            )
            plt.close()
        except:
            print("Could not build mosaic")
            pass



def plot_roc_curve_across_splits(rates : list, save_string : str, dataset : str, config : dict):
    """
    Plot the ROC curve across splits based on the rates

    Args:
        rates: The rates
        save_string: The save string
        dataset: The dataset
        config: The configuration dictionary
    
    Returns:
        None
    """
    fpr_list = [rate[1] for rate in rates]
    tpr_list = [rate[0] for rate in rates]

    mean_fpr = np.linspace(0, 1, 100)
    tprs = []
    aucs = []

    for i in range(len(fpr_list)):
        fpr = fpr_list[i]
        tpr = np.interp(mean_fpr, fpr, tpr_list[i])
        tpr[0] = 0.0
        tprs.append(tpr)
        roc_auc = auc(fpr_list[i], tpr_list[i])
        aucs.append(roc_auc)

    mean_tpr = np.mean(tprs, axis=0)
    mean_tpr[-1] = 1.0
    std_tpr = np.std(tprs, axis=0)

    mean_auc = auc(mean_fpr, mean_tpr)
    std_auc = np.std(aucs)

    # Plot the ROC curve with shaded standard deviation area
    plt.figure()
    plt.plot(mean_fpr, mean_tpr, color='b', label=r'Mean ROC (AUC = %0.2f $\pm$ %0.2f)' % (mean_auc, std_auc), lw=2, alpha=.8)

    tprs_upper = np.minimum(mean_tpr + std_tpr, 1)
    tprs_lower = np.maximum(mean_tpr - std_tpr, 0)
    plt.fill_between(mean_fpr, tprs_lower, tprs_upper, color='grey', alpha=.2, label=r'$\pm$ 1 std. dev.')

    plt.plot([0, 1], [0, 1], color='red', lw=2, linestyle='--', label='Random')
    plt.xlim([-0.05, 1.05])
    plt.ylim([-0.05, 1.05])
    plt.xlabel('False Positive Rate')
    plt.ylabel('True Positive Rate')
    plt.title('Receiver Operating Characteristic')
    plt.legend(loc="lower right")
    os.makedirs(f"experiments/{config['experiment']['project_name']}/visualizations", exist_ok=True)
    plt.savefig(f"experiments/{config['experiment']['project_name']}/visualizations/roc_auc_{save_string}_{dataset}.png")
    plt.close()
    
def plot_survival_auc_across_folds(results: pd.DataFrame, save_string: str, dataset: str, config: dict):
    """
    Plot the survival ROC-AUC across folds based on the results

    Args:
        results: The results
        save_string: The save string
        dataset: The dataset
        config: The configuration dictionary

    Returns:
        None
    """

    all_aucs = []
    times_list = []

    os.makedirs(f"experiments/{config['experiment']['project_name']}/visualizations", exist_ok=True)

    for fold_idx, (durations, events, predictions) in enumerate(results):
        fig, ax = plt.subplots()

        # Ensure durations and events are numpy arrays
        durations = np.asarray(durations)
        events = np.asarray(events)

        # Create a structured array for survival data
        survival_data = np.array([(e, d) for e, d in zip(events, durations)], dtype=[('event', '?'), ('time', '<f8')])

        # Ensure time points are within the follow-up time range
        max_duration = durations.max()
        times = np.linspace(0, max_duration, 100)
        times_list.append(times)

        aucs = []
        for time in times:
            if time >= max_duration:
                continue  # Skip time points that are out of range

            # Calculate AUC and check for validity
            try:
                auc_score = cumulative_dynamic_auc(survival_data, survival_data, predictions, time)[0]
                if not np.isnan(auc_score):
                    aucs.append(auc_score)
            except ZeroDivisionError:
                continue

        if aucs:
            all_aucs.append(np.array(aucs).flatten())  # Ensure the AUC array is flattened
            mean_auc = np.mean(aucs)
            std_auc = np.std(aucs)
            ax.plot(times[:len(aucs)], aucs, label=f'AUC (mean = {mean_auc:.2f}, std = {std_auc:.2f})')

        # Add random model baseline (0.5)
        ax.plot(times, [0.5] * len(times), 'r--', label='Random Model (AUC = 0.5)')
        ax.set_xlim([0, max_duration])
        ax.set_ylim([0, 1])
        ax.set_xlabel('Time')  
        ax.set_ylabel('AUC')
        ax.set_title(f'Time-dependent ROC-AUC for Fold {fold_idx + 1}')
        ax.legend(loc="lower right")

        plt.savefig(f"experiments/{config['experiment']['project_name']}/visualizations/survival_roc_auc_{save_string}_{dataset}_fold_{fold_idx + 1}.png")
        plt.close()

    if all_aucs:
        fig, ax = plt.subplots()
        # Determine the maximum length of the AUC lists
        max_len = max(len(auc) for auc in all_aucs)

        # Pad the aucs lists to have the same length
        padded_aucs = np.full((len(all_aucs), max_len), np.nan)
        for i, auc in enumerate(all_aucs):
            padded_aucs[i, :len(auc)] = auc

        mean_aucs = np.nanmean(padded_aucs, axis=0)
        std_aucs = np.nanstd(padded_aucs, axis=0)
        times = times_list[0]  # Use times from the first split

        ax.plot(times[:len(mean_aucs)], mean_aucs, label=f'Mean AUC (mean = {np.nanmean(mean_aucs):.2f}, std = {np.nanmean(std_aucs):.2f})', color='blue')
        ax.fill_between(times[:len(mean_aucs)], mean_aucs - std_aucs, mean_aucs + std_aucs, color='blue', alpha=0.2)

        # Add random model baseline (0.5)
        ax.plot(times, [0.5] * len(times), 'r--', label='Random Model (AUC = 0.5)')

        ax.set_xlabel('Time')
        ax.set_ylabel('AUC')
        ax.set_title('Time-dependent ROC-AUC (Overall)')
        ax.legend(loc="lower right")

        plt.savefig(f"experiments/{config['experiment']['project_name']}/visualizations/survival_roc_auc_{save_string}_{dataset}_overall.png")
        plt.close()


def plot_precision_recall_across_splits(pr_per_split: list, save_string: str, dataset: str, config: dict):
    """
    Plot the precision-recall curve across splits based on the results

    Args:
        pr_per_split: List of precision-recall curve results per split
        save_string: The save string
        dataset: The dataset
        config: The configuration dictionary

    Returns:
        None
    """
    fig, ax = plt.subplots()
    mean_precisions = []
    mean_recalls = []
    all_precisions = []
    all_recalls = []

    for split_idx, pr_tuple in enumerate(pr_per_split):
        # Check and unpack the tuple
        if isinstance(pr_tuple, list) and len(pr_tuple) == 1:
            pr_tuple = pr_tuple[0]

        if not isinstance(pr_tuple, tuple) or len(pr_tuple) != 2:
            raise ValueError(f"Expected a tuple of (precision, recall) for split {split_idx + 1}, but got {pr_tuple}")

        precisions, recalls = pr_tuple
        mean_precisions.append(np.interp(np.linspace(0, 1, 100), recalls[::-1], precisions[::-1]))
        mean_recalls.append(np.linspace(0, 1, 100))
        all_precisions.append(precisions)
        all_recalls.append(recalls)

    mean_precision = np.mean(mean_precisions, axis=0)
    std_precision = np.std(mean_precisions, axis=0)

    fig, ax = plt.subplots()
    ax.set_xlim([0.0, 1.0])
    ax.set_ylim([0.0, 1.0])
    ax.plot(mean_recalls[0], mean_precision, label='Mean Precision-Recall', color='blue')
    ax.fill_between(mean_recalls[0], mean_precision - std_precision, mean_precision + std_precision, color='blue', alpha=0.2, label='Std Dev')

    ax.set_title('Precision-Recall Curve')
    ax.set_xlabel('Recall')
    ax.set_ylabel('Precision')
    ax.legend(loc="lower left")

    os.makedirs(f"experiments/{config['experiment']['project_name']}/visualizations", exist_ok=True)
    plt.savefig(f"experiments/{config['experiment']['project_name']}/visualizations/precision_recall_{save_string}_{dataset}.png")
    plt.close()

def plot_concordance_index_across_folds(results: pd.DataFrame, save_string: str, dataset: str, config: dict):
    """
    Plot the concordance index across folds based on the results

    Args:
        results: The results
        save_string: The save string
        dataset: The dataset
        config: The configuration dictionary

    Returns:
        None
    """
    fig, ax = plt.subplots()
    times = np.linspace(0, max(durations.max() for durations, _, _ in results), 100)
    all_concordances = []

    for durations, events, predictions in results:
        fold_concordances = []
        for time in times:
            mask = durations >= time
            if mask.sum() == 0:
                fold_concordances.append(np.nan)
            else:
                try:
                    c_index = concordance_index(durations[mask], predictions[mask], events[mask])
                    fold_concordances.append(c_index)
                except ZeroDivisionError:
                    fold_concordances.append(np.nan)
        all_concordances.append(fold_concordances)

    all_concordances = np.array(all_concordances)
    mean_concordances = np.nanmean(all_concordances, axis=0)
    std_concordances = np.nanstd(all_concordances, axis=0)

    
    ax.plot(times, mean_concordances, marker='o', linewidth=1, label='Mean Concordance Index', markersize=3)
    ax.fill_between(times, mean_concordances - std_concordances, mean_concordances + std_concordances, alpha=0.2)
    ax.set_xlim([0, times[-1]])
    ax.set_ylim([0, 1])
    ax.set_title('Concordance Index Over Time')
    ax.set_xlabel('Time')
    ax.set_ylabel('Concordance Index')
    ax.legend()



    os.makedirs(f"experiments/{config['experiment']['project_name']}/visualizations", exist_ok=True)
    plt.savefig(f"experiments/{config['experiment']['project_name']}/visualizations/concordance_index_{save_string}_{dataset}.png")
    plt.close()

def plot_predicted_vs_actual_across_folds(results: pd.DataFrame, save_string: str, dataset: str, config: dict):
    """
    Plot the predicted vs actual values across folds based on the results

    Args:
        results: The results
        save_string: The save string
        dataset: The dataset
        config: The configuration dictionary
    
    Returns:
        None
    """
    all_y_true = []
    all_y_pred = []

    for y_true, y_pred in results:
        y_true = np.asarray(y_true)
        y_pred = np.asarray(y_pred)
        all_y_true.append(y_true)
        all_y_pred.append(y_pred)

    # Determine the maximum length of the y_true and y_pred
    max_len = max(max(len(y) for y in all_y_true), max(len(y) for y in all_y_pred))

    # Pad the y_true and y_pred to the maximum length with np.nan
    padded_y_true = np.full((len(all_y_true), max_len), np.nan)
    padded_y_pred = np.full((len(all_y_pred), max_len), np.nan)

    for i, (y_true, y_pred) in enumerate(zip(all_y_true, all_y_pred)):
        padded_y_true[i, :len(y_true)] = y_true
        padded_y_pred[i, :len(y_pred)] = y_pred

    mean_y_true = np.nanmean(padded_y_true, axis=0)
    mean_y_pred = np.nanmean(padded_y_pred, axis=0)
    std_y_pred = np.nanstd(padded_y_pred, axis=0)

    plt.figure()
    plt.errorbar(mean_y_true, mean_y_pred, yerr=std_y_pred, fmt='o', ecolor='r', capsize=2, label='Mean Predicted vs Actual')
    plt.plot([min(mean_y_true), max(mean_y_true)], [min(mean_y_true), max(mean_y_true)], color='red', linestyle='--')
    plt.xlabel('Actual Values')
    plt.ylabel('Predicted Values')
    plt.title('Predicted vs Actual')
    plt.legend()

    os.makedirs(f"experiments/{config['experiment']['project_name']}/visualizations", exist_ok=True)
    plt.savefig(f"experiments/{config['experiment']['project_name']}/visualizations/predicted_vs_actual_{save_string}_{dataset}.png")
    plt.close()

def plot_calibration(results : pd.DataFrame, save_string : str, dataset : str, config : dict, bins : int = 10):
    """
    Plot the calibration curve based on the results

    Args:
        results: The results
        save_string: The save string
        dataset: The dataset
        config: The configuration dictionary
        bins: The number of bins

    Returns:
        None
    """
    plt.figure()
    for durations, events, predictions in results:
        # Convert predicted log hazards to predicted risks
        predictions = np.exp(predictions)
        predictions = predictions / (1 + predictions)

        true_prob, pred_prob = calibration_curve(events, predictions, n_bins=bins, strategy='uniform')
        plt.plot(pred_prob, true_prob, marker='o', linewidth=1, label=f'{dataset}')

    plt.plot([0, 1], [0, 1], linestyle='--', label='Perfectly calibrated')
    plt.title('Calibration Curve')
    plt.xlabel('Predicted Probability')
    plt.ylabel('Observed Probability')
    plt.legend()
    plt.xlim([0, 1])
    plt.ylim([0, 1])

    os.makedirs(f"experiments/{config['experiment']['project_name']}/visualizations", exist_ok=True)
    plt.savefig(f"experiments/{config['experiment']['project_name']}/visualizations/calibration_{save_string}_{dataset}.png")
    plt.close()

def plot_residuals_across_folds(results: pd.DataFrame, save_string: str, dataset: str, config: dict):
    """
    Plot the residuals across folds based on the results

    Args:
        results: The results
        save_string: The save string
        dataset: The dataset
        config: The configuration dictionary
    
    Returns:
        None
    """

    all_residuals = []

    for y_true, y_pred in results:
        y_true = np.asarray(y_true)
        y_pred = np.asarray(y_pred)
        residuals = y_true - y_pred
        all_residuals.append(residuals)

    # Determine the maximum length of the residuals
    max_len = max(len(residual) for residual in all_residuals)

    # Pad the residuals to the maximum length with np.nan
    padded_residuals = np.full((len(all_residuals), max_len), np.nan)
    for i, residual in enumerate(all_residuals):
        padded_residuals[i, :len(residual)] = residual

    mean_residuals = np.nanmean(padded_residuals, axis=0)
    std_residuals = np.nanstd(padded_residuals, axis=0)

    plt.figure()
    plt.errorbar(np.arange(len(mean_residuals)), mean_residuals, yerr=std_residuals, fmt='o', ecolor='r', capsize=2, label='Mean Residuals')
    plt.axhline(0, color='red', linestyle='--')
    plt.xlabel('Index')
    plt.ylabel('Residuals')
    plt.title('Residual Plot')
    plt.legend()

    os.makedirs(f"experiments/{config['experiment']['project_name']}/visualizations", exist_ok=True)
    plt.savefig(f"experiments/{config['experiment']['project_name']}/visualizations/residuals_{save_string}_{dataset}.png")
    plt.close()

def plot_qq_across_folds(results : pd.DataFrame, save_string : str, dataset : str, config : dict):
    """
    Plot the Q-Q plot across folds based on the results
    Args:
        results: The results
        save_string: The save string
        dataset: The dataset
        config: The configuration dictionary

    Returns:
        None
    """
    plt.figure()
    for i, (y_true, y_pred) in enumerate(results):
        residuals = y_true - y_pred
        stats.probplot(residuals, dist="norm", plot=plt)
    
    plt.title('Q-Q Plot')
    
    os.makedirs(f"experiments/{config['experiment']['project_name']}/visualizations", exist_ok=True)
    plt.savefig(f"experiments/{config['experiment']['project_name']}/visualizations/qq_{save_string}_{dataset}.png")
    plt.close()

def plot_calibration_across_splits(results: pd.DataFrame, save_string: str, dataset: str, config: dict, bins: int = 10):
    """
    Plot the calibration curve across splits based on the results

    Args:
        results: The results
        save_string: The save string
        dataset: The dataset
        config: The configuration dictionary
        bins: The number of bins

    Returns:
        None
    """
    mean_pred_probs = []
    mean_true_probs = []
    all_pred_probs = []
    all_true_probs = []
    
    for durations, events, predictions in results:
        # Convert predicted log hazards to predicted risks
        predictions = np.exp(predictions)
        predictions = predictions / (1 + predictions)

        true_prob, pred_prob = calibration_curve(events, predictions, n_bins=bins, strategy='uniform')

        # Interpolate to a common set of bins
        common_bins = np.linspace(0, 1, bins)
        true_prob_interp = np.interp(common_bins, pred_prob, true_prob)
        pred_prob_interp = common_bins

        mean_pred_probs.append(pred_prob_interp)
        mean_true_probs.append(true_prob_interp)
        all_pred_probs.append(pred_prob_interp)
        all_true_probs.append(true_prob_interp)

    # Calculate the mean and standard deviation across splits
    mean_pred_probs = np.mean(mean_pred_probs, axis=0)
    mean_true_probs = np.mean(mean_true_probs, axis=0)
    std_true_probs = np.std(all_true_probs, axis=0)
    
    plt.figure()
    plt.plot(mean_pred_probs, mean_true_probs, marker='o', linewidth=1, label='Mean Calibration')
    plt.fill_between(mean_pred_probs, mean_true_probs - std_true_probs, mean_true_probs + std_true_probs, alpha=0.2, label='±1 std. dev.')
    plt.plot([0, 1], [0, 1], linestyle='--', label='Perfectly calibrated')
    
    plt.xlim([0, 1])
    plt.ylim([0, 1])
    
    plt.title('Calibration Curve')
    plt.xlabel('Predicted Probability')
    plt.ylabel('Observed Probability')
    plt.legend()

    os.makedirs(f"experiments/{config['experiment']['project_name']}/visualizations", exist_ok=True)
    plt.savefig(f"experiments/{config['experiment']['project_name']}/visualizations/calibration_{save_string}_{dataset}.png")
    plt.close()


def plot_top5_attended_tiles_per_class(slide_name : str, attention_file : str, tfr_directory : str, output_dir : str,
                                       annotation_df : pd.DataFrame, target : str, dataset : str, split : str, save_string : str):
    """
    Plot the top 5 most attended tiles and the top 5 least attended tiles for a given slide

    Args:
        slide_name: The slide name to get the top 5 attended tiles for
        attention_file: The attention file containing the attention map
        tfr_directory: The TFRecord directory
        output_dir: The output directory
        annotation_df: The annotation DataFrame
        target: The target variable
        dataset: The dataset string (val,test,train)
        split: The current cv-split
        save_string: The save string
    
    Returns:
        None
    """
    # Find the corresponding .npz and .tfrecord files
    index_path = os.path.join(tfr_directory, f"{slide_name}.index.npz")
    tfr_path = os.path.join(tfr_directory, f"{slide_name}.tfrecords")

    # Validate the existence of the files
    if not os.path.exists(index_path):
        raise FileNotFoundError(f"Index file not found: {index_path}")
    if not os.path.exists(tfr_path):
        raise FileNotFoundError(f"TFRecord file not found: {tfr_path}")

    # Retrieve the label for the slide from the annotation DataFrame
    label_row = annotation_df.loc[annotation_df['slide'] == slide_name]
    if label_row.empty:
        raise ValueError(f"No label found for slide: {slide_name} in the annotation DataFrame")
    
    label = label_row[target].values[0]

    # Load the attention map
    attention = attention_file['arr_0']

    # Load the TFRecord and its index
    tfr = sf.TFRecord(tfr_path)
    
    # Load the index file, which contains the tile coordinates
    bag_index = np.load(index_path)
    tile_coordinates = bag_index['locations']  # This contains the (x, y) coordinates of the tiles

    logging.info("Bag index shape: %s", tile_coordinates.shape)

    # Get the top 5 attention values and their indices
    top5_attention_indices = np.argsort(attention)[::-1][:5]
    top5_least_attended_indices = np.argsort(attention)[:5]

    # Get the corresponding tile coordinates from the index file
    top5_tile_coordinates = tile_coordinates[top5_attention_indices]
    top5_least_attended_coordinates = tile_coordinates[top5_least_attended_indices]

    # Ensure the output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Plot the top 5 most attended tiles with attention scores
    fig, axs = plt.subplots(1, 5, figsize=(20, 5))
    for i, coord in enumerate(top5_tile_coordinates):
        slide, img = tfr.get_record_by_xy(coord[0], coord[1], decode=True)

        # Convert from Tensor to NumPy array if necessary
        if isinstance(img, torch.Tensor):
            img = img.cpu().numpy()  # No permutation needed, assuming the shape is already [256, 256, 3]

        # Convert to image (RGB assumed)
        img = Image.fromarray(img.astype(np.uint8))  # Convert directly to image

        # Add attention score text to image
        draw = ImageDraw.Draw(img)
        font = ImageFont.load_default()
        draw.text((10, 10), f"Score: {attention[top5_attention_indices[i]]:.4f}", fill="red", font=font)

        # Plot the image
        axs[i].imshow(img)
        axs[i].axis('off')
    plt.suptitle(f"Top 5 most attended tiles ({dataset} {label} {slide_name})", fontsize=21)
    plt.tight_layout()
    plt.savefig(f"{output_dir}/{dataset}_{split}_{label}_{slide_name}_{save_string}_top5_tiles.png")
    plt.close()

    # Plot the top 5 least attended tiles with attention scores
    fig, axs = plt.subplots(1, 5, figsize=(20, 5))
    for i, coord in enumerate(top5_least_attended_coordinates):
        slide, img = tfr.get_record_by_xy(coord[0], coord[1], decode=True)

        # Log image shape
        logging.info("Image shape: %s", img.shape)

        # Convert from Tensor to NumPy array if necessary
        if isinstance(img, torch.Tensor):
            img = img.cpu().numpy()  # No permutation needed, assuming the shape is already [256, 256, 3]

        # Convert to image (RGB assumed)
        img = Image.fromarray(img.astype(np.uint8))  # Convert directly to image

        # Add attention score text to image
        draw = ImageDraw.Draw(img)
        font = ImageFont.load_default()
        draw.text((10, 10), f"Score: {attention[top5_least_attended_indices[i]]:.4f}", fill="red", font=font)

        # Plot the image
        axs[i].imshow(img)
        axs[i].axis('off')
    plt.suptitle(f"Top 5 least attended tiles ({dataset} {label} {slide_name})", fontsize=21)
    plt.tight_layout()
    plt.savefig(f"{output_dir}/{dataset}_{split}_{label}_{slide_name}_{save_string}_least_attended_tiles.png")
    plt.close()