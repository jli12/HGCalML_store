

###
#
#
# for testing: rm -rf TEST; python gravnet.py /eos/cms/store/cmst3/group/hgcal/CMG_studies/gvonsem/hgcalsim/ConverterTask/closeby_1.0To100.0_idsmix_dR0.1_n10_rnd1_s1/dev_LayerClusters_prod2/testconv/dataCollection.dc TEST
#
###


from DeepJetCore.training.training_base import training_base
import keras
from keras.models import Model
from keras.layers import  Dense,Conv1D, Conv2D, BatchNormalization, Multiply, Concatenate #etc
from Layers import GarNet, GravNet, GlobalExchange, CreateZeroMask, SortPredictionByEta, CenterPhi
from DeepJetCore.DJCLayers import ScalarMultiply, Clip, SelectFeatures, Print

from tools import plot_pred_during_training, plot_truth_pred_plus_coords_during_training
import tensorflow as tf

n_gravnet_layers=3 #+1
n_coords=4

def gravnet_model(Inputs,nclasses,nregressions,feature_dropout=0.1):
    
    x = Inputs[0] #this is the self.x list from the TrainData data structure
    
    mask = CreateZeroMask(0)(x)
    
    
    
    #x = CenterPhi(2)(x)
    etas_phis = SelectFeatures(1,3)(x)#eta, phi, just to propagate to the prediction
    
    coords=[]
    
    x = Multiply()([x,mask])
    
    x = BatchNormalization(momentum=0.9)(x)
    x = Multiply()([x,mask])
    x = GarNet(n_aggregators=8, n_filters=64, n_propagate=16, name = 'garnet_pre')(x)
    x = Multiply()([x,mask])
    x, coord = GravNet(n_neighbours=40, n_dimensions=3, n_filters=80, n_propagate=16, 
                       name = 'gravnet_pre',
                       also_coordinates=True)(x)
    coords.append(coord)
    x = BatchNormalization(momentum=0.9)(x)
    x = Multiply()([x,mask])
    
    feats=[]
    for i in range(n_gravnet_layers):
        #x = GlobalExchange()(x)
        x = Concatenate()([x,GlobalExchange()(etas_phis)])
        x = Multiply()([x,mask])
        x = GarNet(n_aggregators=8, n_filters=64, n_propagate=16, name = 'garnet_'+str(i))(x)
        x = Multiply()([x,mask])
        x = Dense(64,activation='elu')(x)
        x = Dense(64,activation='elu')(x)
        x = BatchNormalization(momentum=0.9)(x)
        x = Multiply()([x,mask])
        x = Dense(64,activation='sigmoid')(x)
        x = Multiply()([x,mask])
        x, coord = GravNet(n_neighbours=40, n_dimensions=4, n_filters=80, n_propagate=16, 
                           name = 'gravnet_'+str(i),
                           also_coordinates=True,
                           feature_dropout=feature_dropout
                           )(x)
        coords.append(coord)
        x = BatchNormalization(momentum=0.9)(x)
        x = Multiply()([x,mask])
        feats.append(x)
    
    x = Concatenate()(feats+[x, etas_phis])
    x = Multiply()([x,mask])
    
    x = Dense(64,activation='elu',name='eta_sort')(x)
    x = Dense(64,activation='elu',name='eta_sort2')(x)
    x = Dense(64,activation='elu',name='pre_last_correction')(x)
    x = BatchNormalization(momentum=0.9)(x)
    x = Multiply()([x,mask])
    x = Dense(nregressions,activation=None, kernel_initializer='zeros')(x) 
    #x = Clip(-0.5, 1.5) (x)
    x = Multiply()([x,mask])
    
    x = Concatenate(name="concatlast", axis=-1)([x]+coords+[etas_phis])
    predictions = [x]
    return Model(inputs=Inputs, outputs=predictions)



train=training_base(testrun=False,resumeSilently=True,renewtokens=True)

sampledir = '/eos/cms/store/cmst3/group/hgcal/CMG_studies/hgcalsim/gnn.CreateMLDataset/closeby_1.0To100.0_idsmix_dR0.3_n5_rnd1_s1/hitlist_layercluster/prod5'
samplefile = sampledir+'/tuple_9Of50_n100.meta'
#gets called every epoch
def decay_function(aftern_batches):
    return aftern_batches# int(aftern_batches+5)

plots_after_n_batch=5
use_event=5

ppdts=[ plot_truth_pred_plus_coords_during_training(
               samplefile=samplefile,
               output_file=train.outputDir+'/train_progress'+str(0),
               use_event=use_event,
               x_index = 5,
               y_index = 6,
               z_index = 7,
               e_index = 0,
               pred_fraction_end = 10,
               transformed_x_index = 10, #10,
               transformed_y_index = 11, #11+4*i,
               transformed_z_index = 12, #12+4*i,
               transformed_e_index = None,
               cut_z='pos',
               afternbatches=plots_after_n_batch,
               on_epoch_end=False,
               decay_function=decay_function
               ) ]

ppdts=ppdts+[ plot_truth_pred_plus_coords_during_training(
               samplefile=samplefile,
               output_file=train.outputDir+'/train_progress'+str(i+1),
               use_event=use_event,
               x_index = 5,
               y_index = 6,
               z_index = 7,
               e_index = 0,
               pred_fraction_end = 10,
               transformed_x_index = 13+4*i,
               transformed_y_index = 14+4*i,
               transformed_z_index = 15+4*i,
               transformed_e_index = 16+4*i,
               cut_z='pos',
               afternbatches=plots_after_n_batch,
               on_epoch_end=False,
               decay_function=decay_function
               ) for i in range(n_coords-1) ]


ppdts_callbacks=[ppdts[i].callback for i in range(len(ppdts))]

from Losses import fraction_loss_eta_penalty, fraction_loss, fraction_loss_eta_penalty_card_pen, fraction_loss_noweight, fraction_loss_sorted, fraction_loss_sorted_all, DR_loss, simple_energy_loss

from Losses import Indiv_DR_loss, fraction_loss_eta_penalty_distance_pen, fraction_loss_eta_penalty_sort_both

if not train.modelSet(): # allows to resume a stopped/killed training. Only sets the model if it cannot be loaded from previous snapshot

    #for regression use the regression model
    train.setModel(gravnet_model,feature_dropout=-1)
    
    #read weights where possible from pretrained model
    #import os
    #from DeepJetCore.modeltools import load_model, apply_weights_where_possible
    #m_weights =load_model(os.environ['DEEPJETCORE_SUBPACKAGE'] + '/pretrained/gravnet_1.h5')
    #train.keras_model = apply_weights_where_possible(train.keras_model, m_weights)
    
    #for regression use a different loss, e.g. mean_squared_error
train.compileModel(learningrate=5e-3,
                   loss=fraction_loss_eta_penalty_distance_pen,#fraction_loss)
                   )#clipnorm=1) 
                  
print(train.keras_model.summary())

nbatch=45
verbosity=2

model,history = train.trainModel(nepochs=10, 
                                 batchsize=nbatch,
                                 checkperiod=10, # saves a checkpoint model every N epochs
                                 verbose=verbosity,
                                 additional_callbacks=ppdts_callbacks)


train.change_learning_rate(1e-4)

model,history = train.trainModel(nepochs=10+40, 
                                 batchsize=nbatch,
                                 checkperiod=10, # saves a checkpoint model every N epochs
                                 verbose=verbosity,
                                 additional_callbacks=ppdts_callbacks)



train.change_learning_rate(1e-5)
model,history = train.trainModel(nepochs=50+200, 
                                 batchsize=nbatch,
                                 checkperiod=10, # saves a checkpoint model every N epochs
                                 verbose=verbosity,
                                 additional_callbacks=ppdts_callbacks)


train.change_learning_rate(1e-6)
model,history = train.trainModel(nepochs=250+250, 
                                 batchsize=nbatch,
                                 checkperiod=1, # saves a checkpoint model every N epochs
                                 verbose=verbosity,
                                 additional_callbacks=ppdts_callbacks)



for p in ppdts:
    p.end_job()
exit()

