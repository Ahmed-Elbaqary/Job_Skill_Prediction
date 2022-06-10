import pandas as pd
import os
import pickle
import yaml
import mlflow

#--------------------------------------------------------
LOG_DATA_PKL = "data.pkl"
LOG_MODEL_PKL = "model.pkl"
LOG_METRICS_PKL = "metrics.pkl"
#--------------------------------------------------------


class JobPrediction:
    """Production Class for predicting the probability of a job from skills"""

    # ===================================================
    # ************* Initialization Functions *************
    # ===================================================

    # Constructor
    def __init__(self, mlflow_uri, run_id, clusters_yaml_path):

        # Constants
        self.tracking_uri = mlflow_uri
        self.run_id = run_id

        # Retrieve model and features names
        mlflow_objs = self.load_mlflow_objs()
        self.model = mlflow_objs[0]
        self.features_names = mlflow_objs[1]
        self.targets_names = mlflow_objs[2]

        # Load Clusters config
        self.path_cluster_config = clusters_yaml_path 
        self.skills_clusters_df = self.load_clusters_config(clusters_yaml_path)

    def load_mlflow_objs(self):
        """Load objects from the Mlflow run"""
        #Intialize client and experiment
        mlflow.set_tracking_uri(self.tracking_uri)

        run = mlflow.get_run(self.run_id)
        artifacts_path = run.info.artifact_uri

        # Load data pickle
        data_path = os.path.join(artifacts_path, LOG_DATA_PKL)
        with open(data_path, 'rb') as data_file:
            data_pkl = pickle.load(data_file)
        
        # Load model pickle
        model_path = os.path.join(artifacts_path, LOG_MODEL_PKL)
        with open(model_path, 'rb') as model_file:
            model_pkl = pickle.load(model_file)
        
        # Return data and model objects
        return model_pkl["model_object"], \
               data_pkl["features_names"], \
               data_pkl["targets_names"]

    def load_clusters_config(self, path_cluster_config):
        """Load skills clusters into a dataframe to deal with"""

        # Read yaml file
        with open(path_cluster_config, 'r') as yaml_cluster:
            clusters_config = yaml.safe_load(yaml_cluster)
        
        clusters_df = [(cluster_name, cluster_skill)
                        for cluster_name, cluster_skills in clusters_config.items()
                        for cluster_skill in cluster_skills]
        
        clusters_df = pd.DataFrame(clusters_df,
                                   columns=["cluster_name", "skill"])
        return clusters_df

    # ===================================================
    # ********************* Getters *********************
    # ===================================================
    
    def get_all_skills(self):
        return self.features_names 

    def get_all_jobs(self):
        return self.targets_names 

    # ===================================================
    # ************** Prediction Functions ***************
    # ===================================================

    def create_features_array(self, available_skills):
        """Create the features array from a list of the available skills"""

        # Method's helper functions
        def create_clusters_features(self, available_skills):
            sample_clusters = self.skills_clusters_df.copy()
            sample_clusters["available_skills"] = sample_clusters["skill"].isin(available_skills)
            cluster_features = sample_clusters.groupby("cluster_name")["available_skills"].sum()
            return cluster_features

        def create_skills_features(self, available_skills, excluded_clusters):
            all_features = pd.Series(self.get_all_skills())
            skills_names = all_features[~all_features.isin(excluded_clusters)]
            ohe_skills = pd.Series(skills_names.isin(available_skills).astype(int).tolist(),
                                   index=skills_names)

            return ohe_skills 

        # Method's main function
        cluster_features = create_clusters_features(self, available_skills)
        skills_features = create_skills_features(self, available_skills, cluster_features.index)

        # ... Combine features and sort
        features = pd.concat([skills_features, cluster_features])
        features = features.loc[self.features_names]

        return features.values 

    def predict_jobs_probabilities(self, available_skills):
        """Return probabilities of the different jobs according to available skills"""

        # Create features array
        features_array = self.create_features_array(available_skills)

        # predict and format
        predictions = self.model.predict_proba([features_array])
        predictions = [prob[0][1] for prob in predictions] # to keep positive probabilities
        predictions = pd.Series(predictions, index=self.targets_names).sort_values(ascending=False)

        return predictions 

    # ===================================================
    # ************** Simulation Functions ***************
    # ===================================================
    def recommend_new_skills(self, available_skills, target_job, threshold=0):
        """Given a skill set and want the best skills to learn to become a specific role"""

        # Calculate available skills probabilities
        base_predictions = self.predict_jobs_probabilities(available_skills)

        # Get all possible additionsal skills
        all_skills = pd.Series(self.get_all_skills())
        rest_of_skills = all_skills[~all_skills.isin(available_skills)].copy()

        # Simulate new skills needed 
        simulated_results = []
        for skill in rest_of_skills:
            additional_skill_prob = self.predict_jobs_probabilities([skill] + available_skills)
            additional_skill_uplift = (additional_skill_prob - base_predictions) / base_predictions
            additional_skill_uplift.name = skill 
            simulated_results.append(additional_skill_uplift)

        simulated_results = pd.DataFrame(simulated_results)

        # Recommend new skills with priority 
        target_results = simulated_results[target_job].sort_values(ascending=False)
        positive_mask = (target_results > threshold)
        return target_results[positive_mask]