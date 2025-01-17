import numpy as np
import matplotlib.pyplot as plt
import scipy.io as spio
from  sklearn.preprocessing import MinMaxScaler
import random
import time
import os
from datetime import datetime
from sklearn.metrics import confusion_matrix
import tensorflow as tf
from imblearn.over_sampling import SMOTE
from sklearn.model_selection import train_test_split
import argparse
random.seed(654)
def read_mitbih(filename, max_time=100, classes= ['F', 'N', 'S', 'V', 'Q'], max_nlabel=100):
    def normalize(data):
        data = np.nan_to_num(data)  # removing NaNs and Infs
        data = data - np.mean(data)
        data = data / np.std(data)
        return data

    # read data
    data = []
    samples = spio.loadmat(filename + ".mat")
    samples = samples['s2s_mitbih']
    values = samples[0]['seg_values']
    labels = samples[0]['seg_labels']
    num_annots = sum([item.shape[0] for item in values])

    n_seqs = num_annots / max_time
    #  add all segments(beats) together
    l_data = 0
    for i, item in enumerate(values):
        l = item.shape[0]
        for itm in item:
            if l_data == n_seqs * max_time:
                break
            data.append(itm[0])
            l_data = l_data + 1

    #  add all labels together
    l_lables  = 0
    t_lables = []
    for i, item in enumerate(labels):
        if len(t_lables)==n_seqs*max_time:
            break
        item= item[0]
        for lebel in item:
            if l_lables == n_seqs * max_time:
                break
            t_lables.append(str(lebel))
            l_lables = l_lables + 1

    del values
    data = np.asarray(data)
    shape_v = data.shape
    data = np.reshape(data, [shape_v[0], -1])
    t_lables = np.array(t_lables)
    _data  = np.asarray([],dtype=np.float64).reshape(0,shape_v[1])
    _labels = np.asarray([],dtype=np.dtype('|S1')).reshape(0,)
    for cl in classes:
        _label = np.where(t_lables == cl)
        permute = np.random.permutation(len(_label[0]))
        _label = _label[0][permute[:max_nlabel]]

        # _label = _label[0][:max_nlabel]
        # permute = np.random.permutation(len(_label))
        # _label = _label[permute]
        _data = np.concatenate((_data, data[_label]))
        _labels = np.concatenate((_labels, t_lables[_label]))

    data = _data[:(len(_data)// max_time) * max_time, :]
    _labels = _labels[:(len(_data) // max_time) * max_time]

    # data = _data
    #  split data into sublist of 100=se_len values
    data = [data[i:i + max_time] for i in range(0, len(data), max_time)]
    labels = [_labels[i:i + max_time] for i in range(0, len(_labels), max_time)]
    # shuffle
    permute = np.random.permutation(len(labels))
    data = np.asarray(data)
    labels = np.asarray(labels)
    data= data[permute]
    labels = labels[permute]

    print('Records processed!')

    return data, labels
def evaluate_metrics(confusion_matrix):
    # https://stackoverflow.com/questions/31324218/scikit-learn-how-to-obtain-true-positive-true-negative-false-positive-and-fal
    FP = confusion_matrix.sum(axis=0) - np.diag(confusion_matrix)
    FN = confusion_matrix.sum(axis=1) - np.diag(confusion_matrix)
    TP = np.diag(confusion_matrix)
    TN = confusion_matrix.sum() - (FP + FN + TP)
    # Sensitivity, hit rate, recall, or true positive rate
    TPR = TP / (TP + FN)
    # Specificity or true negative rate
    TNR = TN / (TN + FP)
    # Precision or positive predictive value
    PPV = TP / (TP + FP)
    # Negative predictive value
    NPV = TN / (TN + FN)
    # Fall out or false positive rate
    FPR = FP / (FP + TN)
    # False negative rate
    FNR = FN / (TP + FN)
    # False discovery rate
    FDR = FP / (TP + FP)

    # Overall accuracy
    ACC = (TP + TN) / (TP + FP + FN + TN)
    # ACC_micro = (sum(TP) + sum(TN)) / (sum(TP) + sum(FP) + sum(FN) + sum(TN))
    ACC_macro = np.mean(ACC) # to get a sense of effectiveness of our method on the small classes we computed this average (macro-average)

    return ACC_macro, ACC, TPR, TNR, PPV
def batch_data(x, y, batch_size):
    shuffle = np.random.permutation(len(x))
    start = 0
    #     from IPython.core.debugger import Tracer; Tracer()()
    x = x[shuffle]
    y = y[shuffle]
    while start + batch_size <= len(x):
        yield x[start:start + batch_size], y[start:start + batch_size]
        start += batch_size
def se_block(input_feature, ratio=16):
    # 获取输入特征的通道数
    num_channels = input_feature.shape[-1].value

    # Squeeze操作
    squeeze = tf.reduce_mean(input_feature, axis=[1, 2], keepdims=True)

    # Excitation操作 - 瓶颈结构
    excitation = tf.layers.dense(squeeze, units=num_channels // ratio, activation=tf.nn.relu)
    excitation = tf.layers.dense(excitation, units=num_channels, activation=tf.nn.sigmoid)

    # 重新标定（Scale）
    scale = input_feature * excitation

    return scale
        

def build_network(inputs, dec_inputs,char2numY,n_channels=10,input_depth=280,num_units=128,max_time=10,bidirectional=False):
    # _inputs = tf.reshape(inputs, [-1, n_channels, input_depth / n_channels])
    _inputs = tf.reshape(inputs, [-1, n_channels, tf.cast(input_depth / n_channels, tf.int32)])
    # _inputs = tf.reshape(inputs, [-1,input_depth,n_channels])


    # #(batch*max_time, 280, 1) --> (N, 280, 18)
    conv1 = tf.layers.conv1d(inputs=_inputs, filters=32, kernel_size=2, strides=1,
                             padding='same', activation=tf.nn.relu)
    se1 = se_block(conv1)
    max_pool_1 = tf.layers.max_pooling1d(inputs=se1, pool_size=2, strides=2, padding='same')


    conv2 = tf.layers.conv1d(inputs=max_pool_1, filters=64, kernel_size=2, strides=1,
                             padding='same', activation=tf.nn.relu)
    se2 = se_block(conv2)
    max_pool_2 = tf.layers.max_pooling1d(inputs=se2, pool_size=2, strides=2, padding='same')


    conv3 = tf.layers.conv1d(inputs=max_pool_2, filters=128, kernel_size=2, strides=1,
                              padding='same', activation=tf.nn.relu)
    se3 = se_block(conv3)


    shape = se3.get_shape().as_list()
    data_input_embed = tf.reshape(se3, (-1, max_time,shape[1]*shape[2]))
    logits = tf.layers.dense(data_input_embed, units=len(char2numY), use_bias=True)
    return logits


    

def str2bool(v):
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')




def main():
    parser = argparse.ArgumentParser()

    parser.add_argument('--epochs', type=int, default=500)
    parser.add_argument('--max_time', type=int, default=10)
    parser.add_argument('--test_steps', type=int, default=10)
    parser.add_argument('--batch_size', type=int, default=20)
    parser.add_argument('--data_dir', type=str, default='data/s2s_mitbih_aami')
    parser.add_argument('--bidirectional', type=str2bool, default=str2bool('False'))
    # parser.add_argument('--lstm_layers', type=int, default=2)
    parser.add_argument('--num_units', type=int, default=128)
    parser.add_argument('--n_oversampling', type=int, default=10000)
    parser.add_argument('--checkpoint_dir', type=str, default='checkpoints-5')
    parser.add_argument('--ckpt_name', type=str, default='seq2seq_mitbih.ckpt')
    parser.add_argument('--classes', nargs='+', type=chr,
                        default=['F','N', 'S','V'])
    args = parser.parse_args()
    run_program(args)
def run_program(args):
    print(args)
    max_time = args.max_time # 5 3 second best 10# 40 # 100
    epochs = args.epochs # 300
    batch_size = args.batch_size # 10
    num_units = args.num_units
    bidirectional = args.bidirectional
    # lstm_layers = args.lstm_layers
    n_oversampling = args.n_oversampling
    checkpoint_dir = args.checkpoint_dir
    ckpt_name = args.ckpt_name
    test_steps = args.test_steps
    classes= args.classes
    filename = args.data_dir

    X, Y = read_mitbih(filename,max_time,classes=classes,max_nlabel=100000) #11000
    print ("# of sequences: ", len(X))
    input_depth = X.shape[2]
    n_channels = 10
    classes = np.unique(Y)
    char2numY = dict(zip(classes, range(len(classes))))
    n_classes = len(classes)
    print ('Classes: ', classes)
    for cl in classes:
        ind = np.where(classes == cl)[0][0]
        print (cl, len(np.where(Y.flatten()==cl)[0]))
    # char2numX['<PAD>'] = len(char2numX)
    # num2charX = dict(zip(char2numX.values(), char2numX.keys()))
    # max_len = max([len(date) for date in x])
    #
    # x = [[char2numX['<PAD>']]*(max_len - len(date)) +[char2numX[x_] for x_ in date] for date in x]
    # print(''.join([num2charX[x_] for x_ in x[4]]))
    # x = np.array(x)

    char2numY['<GO>'] = len(char2numY)
    num2charY = dict(zip(char2numY.values(), char2numY.keys()))

    Y = [[char2numY['<GO>']] + [char2numY[y_] for y_ in date] for date in Y]
    Y = np.array(Y)

    x_seq_length = len(X[0])
    y_seq_length = len(Y[0])- 1

    # Placeholders
    inputs = tf.placeholder(tf.float32, [None, max_time, input_depth], name = 'inputs')
    targets = tf.placeholder(tf.int32, (None, None), 'targets')
    dec_inputs = tf.placeholder(tf.int32, (None, None), 'output')

    # logits = build_network(inputs,dec_inputs=dec_inputs)
    logits = build_network(inputs, dec_inputs, char2numY, n_channels=n_channels, input_depth=input_depth, num_units=num_units, max_time=max_time,
                  bidirectional=bidirectional)
    # decoder_prediction = tf.argmax(logits, 2)
    # confusion = tf.confusion_matrix(labels=tf.argmax(targets, 1), predictions=tf.argmax(logits, 2), num_classes=len(char2numY) - 1)# it is wrong
    # mean_accuracy,update_mean_accuracy = tf.metrics.mean_per_class_accuracy(labels=targets, predictions=decoder_prediction, num_classes=len(char2numY) - 1)

    with tf.name_scope("optimization"):
        # Loss function
        vars = tf.trainable_variables()
        beta = 0.001
        lossL2 = tf.add_n([tf.nn.l2_loss(v) for v in vars
                            if 'bias' not in v.name]) * beta
        loss = tf.contrib.seq2seq.sequence_loss(logits, targets, tf.ones([batch_size, y_seq_length]))
        # Optimizer
        loss = tf.reduce_mean(loss + lossL2)
        optimizer = tf.train.RMSPropOptimizer(1e-3).minimize(loss)

    # split the dataset into the training and test sets
    X_train, X_test, y_train, y_test = train_test_split(X, Y, test_size=0.2, random_state=42)

    # over-sampling: SMOTE
    X_train = np.reshape(X_train,[X_train.shape[0]*X_train.shape[1],-1])
    y_train= y_train[:,1:].flatten()

    nums = []
    for cl in classes:
        ind = np.where(classes == cl)[0][0]
        nums.append(len(np.where(y_train.flatten()==ind)[0]))
    # ratio={0:nums[3],1:nums[1],2:nums[3],3:nums[3]} # the best with 11000 for N
    ratio={0:n_oversampling,1:nums[1],2:n_oversampling,3:n_oversampling}
    sm = SMOTE(random_state=12,ratio=ratio)
    X_train, y_train = sm.fit_sample(X_train, y_train)

    X_train = X_train[:(X_train.shape[0]//max_time)*max_time,:]
    y_train = y_train[:(X_train.shape[0]//max_time)*max_time]

    X_train = np.reshape(X_train,[-1,X_test.shape[1],X_test.shape[2]])
    y_train = np.reshape(y_train,[-1,y_test.shape[1]-1,])
    y_train= [[char2numY['<GO>']] + [y_ for y_ in date] for date in y_train]
    y_train = np.array(y_train)

    print ('Classes in the training set: ', classes)
    for cl in classes:
        ind = np.where(classes == cl)[0][0]
        print (cl, len(np.where(y_train.flatten()==ind)[0]))
    print ("------------------y_train samples--------------------")
    for ii in range(2):
      print(''.join([num2charY[y_] for y_ in list(y_train[ii+5])]))
    print ("------------------y_test samples--------------------")
    for ii in range(2):
      print(''.join([num2charY[y_] for y_ in list(y_test[ii+5])]))

    def test_model():
        # source_batch, target_batch = next(batch_data(X_test, y_test, batch_size))
        acc_track = []
        sum_test_conf = []
        for batch_i, (source_batch, target_batch) in enumerate(batch_data(X_test, y_test, batch_size)):

            dec_input = np.zeros((len(source_batch), 1)) + char2numY['<GO>']
            for i in range(y_seq_length):
                batch_logits = sess.run(logits,
                                        feed_dict={inputs: source_batch, dec_inputs: dec_input})
                prediction = batch_logits[:, -1].argmax(axis=-1)
                dec_input = np.hstack([dec_input, prediction[:, None]])
            # acc_track.append(np.mean(dec_input == target_batch))
            acc_track.append(dec_input[:, 1:] == target_batch[:, 1:])
            y_true= target_batch[:, 1:].flatten()
            y_pred = dec_input[:, 1:].flatten()
            sum_test_conf.append(confusion_matrix(y_true, y_pred,labels=range(len(char2numY)-1)))

        sum_test_conf= np.mean(np.array(sum_test_conf, dtype=np.float32), axis=0)

        # print('Accuracy on test set is: {:>6.4f}'.format(np.mean(acc_track)))

        # mean_p_class, accuracy_classes = sess.run([mean_accuracy, update_mean_accuracy],
        #                                           feed_dict={inputs: source_batch,
        #                                                      dec_inputs: dec_input[:, :-1],
        #                                                      targets: target_batch[:, 1:]})
        # print (mean_p_class)
        # print (accuracy_classes)
        acc_avg, acc, sensitivity, specificity, PPV = evaluate_metrics(sum_test_conf)
        print('Average Accuracy is: {:>6.4f} on test set'.format(acc_avg))
        for index_ in range(n_classes):
            print("\t{} rhythm -> Sensitivity: {:1.4f}, Specificity : {:1.4f}, Precision (PPV) : {:1.4f}, Accuracy : {:1.4f}".format(classes[index_],
                                                                                                          sensitivity[
                                                                                                              index_],
                                                                                                          specificity[
                                                                                                              index_],PPV[index_],
                                                                                                          acc[index_]))
        print("\t Average -> Sensitivity: {:1.4f}, Specificity : {:1.4f}, Precision (PPV) : {:1.4f}, Accuracy : {:1.4f}".format(np.mean(sensitivity),np.mean(specificity),np.mean(PPV),np.mean(acc)))
        return acc_avg, acc, sensitivity, specificity, PPV
    loss_track = []
    def count_prameters():
        print ('# of Params: ', np.sum([np.prod(v.get_shape().as_list()) for v in tf.trainable_variables()]))

    count_prameters()

    if (os.path.exists(checkpoint_dir) == False):
        os.mkdir(checkpoint_dir)
    # train the graph
    with tf.Session() as sess:
        sess.run(tf.global_variables_initializer())
        sess.run(tf.local_variables_initializer())
        saver = tf.train.Saver()
        print(str(datetime.now()))
        ckpt = tf.train.get_checkpoint_state(checkpoint_dir)
        pre_acc_avg = 0.0
        if ckpt and ckpt.model_checkpoint_path:
            # # Restore
            ckpt_name = os.path.basename(ckpt.model_checkpoint_path)
            # saver.restore(session, os.path.join(checkpoint_dir, ckpt_name))
            saver.restore(sess, tf.train.latest_checkpoint(checkpoint_dir))
            # or 'load meta graph' and restore weights
            # saver = tf.train.import_meta_graph(ckpt_name+".meta")
            # saver.restore(session,tf.train.latest_checkpoint(checkpoint_dir))
            test_model()
        else:

            for epoch_i in range(epochs):
                start_time = time.time()
                train_acc = []
                for batch_i, (source_batch, target_batch) in enumerate(batch_data(X_train, y_train, batch_size)):
                    _, batch_loss, batch_logits = sess.run([optimizer, loss, logits],
                        feed_dict = {inputs: source_batch,
                                     dec_inputs: target_batch[:, :-1],
                                     targets: target_batch[:, 1:]})
                    loss_track.append(batch_loss)
                    train_acc.append(batch_logits.argmax(axis=-1) == target_batch[:,1:])
                # mean_p_class,accuracy_classes = sess.run([mean_accuracy,update_mean_accuracy],
                #                         feed_dict={inputs: source_batch,
                #                                               dec_inputs: target_batch[:, :-1],
                #                                               targets: target_batch[:, 1:]})

                # accuracy = np.mean(batch_logits.argmax(axis=-1) == target_batch[:,1:])
                accuracy = np.mean(train_acc)
                print('Epoch {:3} Loss: {:>6.3f} Accuracy: {:>6.4f} Epoch duration: {:>6.3f}s'.format(epoch_i, batch_loss,
                                                                                  accuracy, time.time() - start_time))

                if epoch_i%test_steps==0:
                    acc_avg, acc, sensitivity, specificity, PPV= test_model()

                    print('loss {:.4f} after {} epochs (batch_size={})'.format(loss_track[-1], epoch_i + 1, batch_size))
                    save_path = os.path.join(checkpoint_dir, ckpt_name)
                    saver.save(sess, save_path)
                    print("Model saved in path: %s" % save_path)

                    # if np.nan_to_num(acc_avg) > pre_acc_avg:  # save the better model based on the f1 score
                    #     print('loss {:.4f} after {} epochs (batch_size={})'.format(loss_track[-1], epoch_i + 1, batch_size))
                    #     pre_acc_avg = acc_avg
                    #     save_path =os.path.join(checkpoint_dir, ckpt_name)
                    #     saver.save(sess, save_path)
                    #     print("The best model (till now) saved in path: %s" % save_path)

            plt.plot(loss_track)
            plt.show()
        print(str(datetime.now()))
        # test_model()
if __name__ == '__main__':
    main()

