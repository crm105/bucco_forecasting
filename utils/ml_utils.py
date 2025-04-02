from sklearn.calibration import calibration_curve
import matplotlib.pyplot as plt
import seaborn as sns

def mse(y, y_hat):
    """Calculate mean squared error given true and prediction arrays
    Args:
        y (array-like): Array of true target values
        y_hat (array-like): Array of model predicted target values

        Returns:
            float: Mean squared error
    """
    return sum((y - y_hat)**2)/len(y)

def plot_calibration_curve(y, y_hat, n_bins = 25):
    """ Produces score calibration curve given true and predicted values
    Args:
        y (array-like): Array of true target values
        y_hat (array-lie): Array of model predicted target values
        n_bins (int): Number of discrete bins segment calibration curve

    returns:
        matplotlib.figure.Figure: Calibration curve
    """

    fop, mpv = calibration_curve(y, y_hat, n_bins=n_bins)
    fig, ax = plt.subplots()

    sns.lineplot(x = mpv, y = fop, color = 'blue', marker = 'o', ax = ax)

    # Plot the first line
    ax.plot([0,1], [0,1], linestyle = '--', color = 'black')
    ax.set_xlim(0,1)
    ax.set_ylim(0,1)

    return fig

class aModelQC:
    def __init__(self, model, X_validation, y_validation, X_test = None, y_test = None):
        """
        Produces and stores model validation artifacts
        Args:
            model (xgboost.sklearn.XGBClassifier) : Trained XGBoost model
            X_validation (array-like): Validation set features
            y_validation (array-like): Validation set target
            X_test (array-like): Holdout test set features
            y_test (array-like): Holdout test set target
        """
        self.model = model
        self.X_validation = X_validation
        self.y_validation = y_validation
        self.X_test = X_test
        self.y_test = y_test
        self.y_val_pred = self.model.predict_proba(X_validation)[:,1]

        if X_test:
            self.y_test_pred = self.model.predict_proba(X_test)[:,1]

        self.validation_accuracy = model.score(X_validation.to_numpy(), y_validation.to_numpy())
        #brier score is MSE in a two class case
        self.brier_score = mse(self.y_validation, self.y_val_pred)

        self.calibration_curve = plot_calibration_curve(self.y_validation, self.y_val_pred)
